import sys, os

import csv
import networkx as nx
#



#Add all paths
sys.path.insert(0, os.path.abspath('..'))
from Tools import *
from Domain import *

########################################################
# Robert Klein, Alborz Geramifard Nov 26 2012 at MIT #
########################################################
# Persistent Search and Track Mission with:
# NUM_UAV:       num vehicles present
# NUM_COMMS_LOC  num intermediate communication states
# Other associated parameters shown below.
#
#   Goal is to maintain as many UAVs with functional
# sensor and actuator as possible in the
# surveillance state, while maintaining at least 1 UAV
# with working actuator in each communication state.
#
#   Failure to satisfy the communication state above
# results in zero reward earned for surveillance.
#
#   State vector consists of blocks of 4 states,
# corresponding to each UAV:
# [location, fuel qty, actuator status, sensor status]
#   so for example, state [1,9,1,1,2,3,0,1] -->
# [1,9,1,1 || 2,3,0,1] --> 2 UAV's;
#   UAV1 in location 1, with 9 fuel units remaining, and
# sensor + actuator with status 1 (defined in the classes below).
#   UAV 2 in location 2, 3 fuel units remaining, actuator
# with status 0 and sensor with status 1.
#
#   Location transitions, sensor and actuator failures, and
# fuel consumption are stochastic.
########################################################

# NOTE Visualization relies on fact that "Crashed" state is the final one.
class UAVLocation:
    BASE_LOC = 0
    NUM_COMMS_LOC = 1 # Each comms location implicitly lies on [1, SIZE - 3]
    SIZE = 3 + NUM_COMMS_LOC   # Manually inputted
    # Possible location states, excluding communicatinons
    SURVEIL_LOC = SIZE-2
    CRASHED = SIZE-1
class ActuatorState:
    FAILED, RUNNING = 0,1 # Status of actuator
    SIZE = 2
class SensorState:
    FAILED, RUNNING = 0,1 # Status of sensor
    SIZE = 2
class UAVAction:
    ADVANCE,RETREAT,LOITER = 2,0,1 # Available actions
    SIZE = 3 # number of states above

class UAVIndex:
    UAV_LOC, UAV_FUEL, UAV_ACT_STATUS, UAV_SENS_STATUS = 0,1,2,3
    SIZE = 4 # Number of indices required for state of each UAV
    
#class UAVDispObject:
#    UAV_RADIUS = 0.3
#    uav_id = -1
#    location = 0
#    fuel_qty = 0
#    sensor_status = 0
#    actuator_status = 0
#    vis_position = None
#    circle_obj = None
#    sensor_obj = None
#    actuator_obj = None
#    def __init__(self, uav_id = -1):
#        self.uav_id = uav_id
#    def setState(self,s):
#        self.location = s[UAVIndex.UAV_LOC]
#        self.fuel_qty = s[UAVIndex.UAV_FUEL]
#        self.sensor_status = s[UAVIndex.UAV_SENS_STATUS]
#        self.actuator_status = s[UAVIndex.UAV_ACT_STATUS]
#        self.vis_position = (self.location, 1 + self.uav_id)
#    def getCircleObject(self):
#        return mpatches.Circle(self.vis_position, self.UAV_RADIUS, fc="w")
#    def getTextObj(self):
#        return pl.text(location[0], location[1], fuel_qty)
#    def removeObjectsFromVis(self):
#        self.circle_obj.remove()
#        self.sensor_obj.remove()
#        self.actuator_obj.remove()
        

class PST(Domain):
    
    episodeCap = 100 # 100 used in tutorial
    
    FULL_FUEL = 10 # Number of fuel units at start
    P_NOM_FUEL_BURN = 0.8 # Probability of nominal (1 unit) fuel burn on timestep
 #   P_TWO_FUEL_BURN = 1.0 - P_NOM_FUEL_BURN # Probability of 2-unit fuel burn on timestep
    P_ACT_FAIL = 0.02 # Probability that actuators fail on this timestep
    P_SENSOR_FAIL = 0.05 #Probability that sensors fail on this timestep
    CRASH_REWARD_COEFF = -2.0 # Negative reward coefficient for running out of fuel (applied on every step) [C_crash]
    SURVEIL_REWARD_COEFF = 1.5 # Positive reward coefficient for performing surveillance on each step [C_cov]
    FUEL_BURN_REWARD_COEFF = 0.0 # Negative reward coefficient: for fuel burn penalty, not mentioned in MDP Tutorial
    numCrashed = 0 # Number of crashed UAVs [n_c]
    numHealthySurveil = 0 #Number of UAVs in surveillance area with working sensor and actuator [n_s]
    commsAvailable = 0 #1 if at least 1 UAV is in comms area with healthy sensor [I_comm]
    fuelUnitsBurned = 0
    LIMITS = []
    
    NUM_UAV = 0 # Number of UAVs present in the mission
    REFUEL_RATE = 1 # Rate of refueling per timestep
    NOM_FUEL_BURN = 1 # Nominal rate of fuel depletion selected with probability P_NOM_FUEL_BURN
    STOCH_FUEL_BURN = 2 # Alternative fuel burn rate
    
    isCommStatesCovered = False # All comms states are covered
    
    # Plotting constants
    UAV_RADIUS = 0.3
    SENSOR_REL_X = 0.2 # Location of the sensor image relative to the uav
    SENSOR_LENGTH = 0.2 # Height of the sensor 'antenna' image
    ACTUATOR_REL_Y = 0.2 # Location of the sensor image relative to the uav
    ACTUATOR_HEIGHT = 0.2 # Height of the sensor 'antenna' image
    domain_fig = None
    subplot_axes = None
    location_rect_vis = None # List of rectangle objects used in the plot
    uav_circ_vis = None
    uav_text_vis = None
    uav_sensor_vis = None
    uav_actuator_vis = None
    location_coord = None # Coordinates of the center of each rectangle
#    uav_vis_list = None # List of UAV objects used in plot
    LOCATION_WIDTH = 1.0 # Width of each rectangle used to represent a location
    RECT_GAP = 1.0   # Gap to leave between rectangles
    
    ###
    
    def __init__(self, NUM_UAV = 6, motionNoise = 0):
        self.NUM_UAV                = NUM_UAV
        self.states_num             = NUM_UAV * UAVIndex.SIZE       # Number of states (UAV_LOC, UAV_FUEL...)
        self.actions_num            = pow(UAVAction.SIZE,NUM_UAV)    # Number of Actions: ADVANCE, RETREAT, LOITER
        _statespace_limits = vstack([[0,UAVLocation.SIZE-1],[0,self.FULL_FUEL-1],[0,ActuatorState.SIZE-1],[0,SensorState.SIZE-1]]) # 3 Location states, 2 status states
        self.statespace_limits      = tile(_statespace_limits,(NUM_UAV,1))# Limits of each dimension of the state space. Each row corresponds to one dimension and has two elements [min, max]
        self.motionNoise = motionNoise # with some noise, when uav desires to transition to new state, remains where it is (loiter)
        self.LIMITS                 = tile(UAVAction.SIZE, (1,NUM_UAV))[0] # eg [3,3,3,3]
        self.isCommStatesCovered    = False # Don't have communications available yet, so no surveillance reward allowed.
        self.location_rect_vis          = None # 
        self.location_coord         = None
        self.uav_circ_vis           = None
        self.uav_text_vis = None
        self.uav_sensor_vis = None
        self.uav_actuator_vis = None
#        self.SENSOR_REL_X = self.UAV_RADIUS - self.SENSOR_LENGTH
#        self.ACTUATOR_REL_Y = self.UAV_RADIUS - self.ACTUATOR_HEIGHT
#        state_space_dims = None # Number of dimensions of the state space
#        episodeCap = None       # The cap used to bound each episode (return to s0 after)
        super(PST,self).__init__()
    def showDomain(self,s,a = 0):
        
         #Draw the environment
         # Allocate horizontal 'lanes' for UAVs to traverse
        if self.location_rect_vis is None:
            # Figure with x width corresponding to number of location states, UAVLocation.SIZE
            # and rows (lanes) set aside in y for each UAV (NUM_UAV total lanes).  Add buffer of 1
            distBetweenLocations = self.RECT_GAP + self.LOCATION_WIDTH
            self.domain_fig = pl.figure(1, (UAVLocation.SIZE * distBetweenLocations + 1, self.NUM_UAV + 1))
            self.subplot_axes = self.domain_fig.add_axes([0, 0, 1, 1], frameon=False, aspect=1.)
            self.subplot_axes.set_xlim(0, 1 + UAVLocation.SIZE * distBetweenLocations)
            self.subplot_axes.set_ylim(0, 1 + self.NUM_UAV)
            self.subplot_axes.xaxis.set_visible(False)
            self.subplot_axes.yaxis.set_visible(False)
            middleFigure = self.NUM_UAV / 2.0 # Y coordinate at the middle of the figure
            # Assign coordinates of each possible uav location on figure
            self.location_coord = [0.5 + (self.LOCATION_WIDTH / 2) + (distBetweenLocations)*i for i in range(UAVLocation.SIZE-1)]
            self.location_coord.append(2*UAVLocation.SIZE-0.5 + self.LOCATION_WIDTH / 2)
             # Create rectangular patches at each of those locations
            self.location_rect_vis = [mpatches.Rectangle([0.5 + (distBetweenLocations)*i, 0], self.LOCATION_WIDTH, self.NUM_UAV * 2, fc = 'w') for i in range(UAVLocation.SIZE-1)]
            self.location_rect_vis.append(mpatches.Rectangle([2*UAVLocation.SIZE-0.5, 0], self.LOCATION_WIDTH, self.NUM_UAV * 2, fc = 'r'))
            [self.subplot_axes.add_patch(self.location_rect_vis[i]) for i in range(4)]
            # Initialize list of circle objects
            
            uav_x = self.location_coord[UAVLocation.BASE_LOC]
            
#            self.uav_vis_list = [UAVDispObject(uav_id) for uav_id in range(0,self.NUM_UAV)]
            self.uav_circ_vis = [mpatches.Circle((uav_x,1+uav_id), self.UAV_RADIUS, fc="w") for uav_id in range(0,self.NUM_UAV)]
            self.uav_text_vis = [pl.text(0, 0, 0) for uav_id in range(0,self.NUM_UAV)]
            self.uav_sensor_vis = [mpatches.Wedge((uav_x+self.SENSOR_REL_X, 1+uav_id),self.SENSOR_LENGTH, -30, 30) for uav_id in range(0,self.NUM_UAV)]
            self.uav_actuator_vis =[mpatches.Wedge((uav_x, 1+uav_id + self.ACTUATOR_REL_Y),self.ACTUATOR_HEIGHT, 60, 120) for uav_id in range(0,self.NUM_UAV)]
            pl.show(block=False)
            

                      # For each UAV:
         # Draw a circle, with text inside = amt fuel remaining
         # Triangle on top of UAV for comms, black = good, red = bad
         # Triangle below UAV for surveillance
         
         # Remove all UAV circle objects from visualization
        else:
            [self.uav_circ_vis[uav_id].remove() for uav_id in range(0,self.NUM_UAV)]
            [self.uav_text_vis[uav_id].remove() for uav_id in range(0,self.NUM_UAV)]
#            [self.uav_sensor_vis[uav_id].remove() for uav_id in range(0,self.NUM_UAV)]
        for uav_id in range(0,self.NUM_UAV):
            uav_ind = uav_id * UAVIndex.SIZE
            uav_location = s[uav_ind + UAVIndex.UAV_LOC] # State index corresponding to the location of this uav
            uav_fuel = s[uav_ind + UAVIndex.UAV_FUEL]
            uav_sensor = s[uav_ind + UAVIndex.UAV_SENS_STATUS]
            uav_actuator = s[uav_ind + UAVIndex.UAV_ACT_STATUS]
            
            uav_x = self.location_coord[uav_location]
            uav_y = 1 + uav_id
            
            self.uav_circ_vis[uav_id] = mpatches.Circle((uav_x,uav_y), self.UAV_RADIUS, fc="w")
            self.uav_text_vis[uav_id] = pl.text(uav_x-0.05, uav_y-0.05, uav_fuel)
            if uav_sensor == SensorState.RUNNING: objColor = 'black'
            else: objColor = 'red'
            self.uav_sensor_vis[uav_id] = mpatches.Wedge((uav_x+self.SENSOR_REL_X,uav_y),self.SENSOR_LENGTH, -30, 30, color=objColor)
            
            if uav_actuator == ActuatorState.RUNNING: objColor = 'black'
            else: objColor = 'red'
            self.uav_actuator_vis[uav_id] = mpatches.Wedge((uav_x,uav_y + self.ACTUATOR_REL_Y),self.ACTUATOR_HEIGHT, 60, 120, color=objColor)
            
            self.subplot_axes.add_patch(self.uav_circ_vis[uav_id])
            self.subplot_axes.add_patch(self.uav_sensor_vis[uav_id])
            self.subplot_axes.add_patch(self.uav_actuator_vis[uav_id])
            
             
#for i in range(self.chainSize):
#               ax.add_patch(self.circles[i])
#               if i != self.chainSize-1:
#                    fromAtoB(1+2*i+self.SHIFT,self.Y+self.SHIFT,1+2*(i+1)-self.SHIFT, self.Y+self.SHIFT)
#                    if i != self.chainSize-2: fromAtoB(1+2*(i+1)-self.SHIFT,self.Y-self.SHIFT,1+2*i+self.SHIFT, self.Y-self.SHIFT, 'r')
#               fromAtoB(.75,self.Y-1.5*self.SHIFT,.75,self.Y+1.5*self.SHIFT,'r',connectionstyle='arc3,rad=-1.2')
#               pl.show(block=False)
#            
#        [p.set_facecolor('w') for p in self.circles]
#        self.circles[s].set_facecolor('k')

        pl.draw()
        sleep(1)
#===============================================================================
    def showLearning(self,representation):
        pass
    def step(self,s,a):
        ns = s # no concerns about affecting state mid-step here
        actionVector = id2vec(a,self.LIMITS) # returns list of form [0,1,0,2] corresponding to action of each uav
        print 'action vector selected:',actionVector
        
        # Create array with value 0 in all states corresponding to comms locations
        # Update this while iterate over each UAV; used to determine if comms link is functioning
        # i.e., all communications states are occupied by UAVs with functioning actuators and sensors
        commStatesCovered = [0] * UAVLocation.SIZE
        commStatesCovered[UAVLocation.BASE_LOC] = 1
        commStatesCovered[UAVLocation.CRASHED] = 1
        commStatesCovered[UAVLocation.SURVEIL_LOC] = 1
        
        self.numHealthySurveil = 0
        self.fuelUnitsBurned = 0
        
        for uav_id in range(0,self.NUM_UAV):            
            uav_ind = uav_id * UAVIndex.SIZE
            uav_location_ind = uav_ind + UAVIndex.UAV_LOC # State index corresponding to the location of this uav
            # First check for crashing uavs; short-circuit the loop
            if(s[uav_location_ind] == UAVLocation.CRASHED):
                continue
            
            uav_fuel_ind = uav_ind + UAVIndex.UAV_FUEL
            uav_sensor_ind = uav_ind + UAVIndex.UAV_SENS_STATUS
            uav_actuator_ind = uav_ind + UAVIndex.UAV_ACT_STATUS
            
            uav_action = actionVector[uav_id]
            ##### STATE TRANSITIONS #####            
            # Position state transition
            if(uav_action == UAVAction.ADVANCE):
                if(random.random() > self.motionNoise): # With some noise, don't transition to new state
                    ns[uav_location_ind] += 1
            elif(uav_action == UAVAction.RETREAT):
                if(random.random() > self.motionNoise): # With some noise, don't transition to new state
                    ns[uav_location_ind] -= 1
            # else, action is loiter, no motion taken.
            
            if (ns[uav_location_ind] != UAVLocation.BASE_LOC): # Not at base, failures can occur
                # Fuel burn transition
                if(random.random() < self.P_NOM_FUEL_BURN):
                    ns[uav_fuel_ind] -= self.NOM_FUEL_BURN
                    self.fuelUnitsBurned += self.NOM_FUEL_BURN
                else:
                    ns[uav_fuel_ind] -= self.STOCH_FUEL_BURN
                    self.fuelUnitsBurned += self.STOCH_FUEL_BURN
                
                # Sensor failure transition
                if(random.random() < self.P_SENSOR_FAIL):
                    ns[uav_sensor_ind] = SensorState.FAILED
                    print 'UAV',uav_id,'Failed sensor!'
               
                # Actuator failure transition
                if(random.random() < self.P_ACT_FAIL):
                    ns[uav_actuator_ind] = ActuatorState.FAILED
                    print '### UAV',uav_id,'Failed actuator! ###'
                
                if (ns[uav_fuel_ind] < 1): # We just crashed a UAV! Failed to get back to base after action a
                    self.numCrashed += 1
                    ns[uav_location_ind] = UAVLocation.CRASHED
                    print '########### UAV',uav_id,'has crashed! ############'
                    continue
                
                if(ns[uav_actuator_ind] == ActuatorState.RUNNING): # If actuator works, comms are available in this state
                    commStatesCovered[ns[uav_location_ind]] = 1
                    # If actuator and sensor works, surveillance available in this state
                    # If this uav is also in the surveillance region, then increment the number of uavs available for surveilance
                    if((ns[uav_location_ind] == UAVLocation.SURVEIL_LOC) and (ns[uav_sensor_ind] == SensorState.RUNNING)):
                          self.numHealthySurveil += 1
                
            else: # We transitioned to or loitered in Base
                ns[uav_fuel_ind] += self.REFUEL_RATE
                ns[uav_fuel_ind] = bound(ns[uav_fuel_ind], 0, self.FULL_FUEL)
                ns[uav_sensor_ind] = SensorState.RUNNING;
                ns[uav_actuator_ind] = ActuatorState.RUNNING;
                print 'UAV',uav_id,'at base.'
        
        ##### Compute reward #####
        totalStepReward = 0
        self.updateCommsCoverage(commStatesCovered) # Update member variable corresponding 
        if(self.isCommStatesCovered == True):
            totalStepReward += self.SURVEIL_REWARD_COEFF * self.numHealthySurveil
        totalStepReward += self.CRASH_REWARD_COEFF * self.numCrashed
        totalStepReward += self.FUEL_BURN_REWARD_COEFF * self.fuelUnitsBurned # Presently this component is set to zero.
 
        return totalStepReward,ns,self.NOT_TERMINATED
        # Returns the triplet [r,ns,t] => Reward, next state, isTerminal
    # Update member variable indicating if comms link is available, ie, if at least
    #1 uav with working sensor or actuator exists in each comms region
    def updateCommsCoverage(self, commStatesCovered):
        if(sum(commStatesCovered) == UAVLocation.SIZE): # All comms states have at least 1 functional UAV [I_comm = 1]
            self.commStatesCovered = True
        else: self.commStatesCovered = False
    def s0(self):
        returnList = []
        for dummy in range(0,self.NUM_UAV):
            returnList = returnList + [UAVLocation.BASE_LOC, self.FULL_FUEL, ActuatorState.RUNNING, SensorState.RUNNING]
        return returnList # Omits final index
    def possibleActions(self,s):
        # return the id of possible actions
        # find empty blocks (nothing on top)
        validActions = [] # Contains a list of uav_actions lists, e.g. [[0,1,2],[0,1],[1,2]] with the index corresponding to a uav.
        # First, enumerate the possible actions for each uav
        for uav_id in range(0,self.NUM_UAV):
            uav_actions = []
            uav_ind = uav_id * UAVIndex.SIZE
            uav_location = s[uav_ind + UAVIndex.UAV_LOC] # State index corresponding to the location of this uav
            uav_fuel = s[uav_ind + UAVIndex.UAV_FUEL]
            uav_sensor = s[uav_ind + UAVIndex.UAV_SENS_STATUS]
            uav_actuator = s[uav_ind + UAVIndex.UAV_ACT_STATUS]
            
            uav_actions.append(UAVAction.LOITER)
            
            if (uav_location == UAVLocation.CRASHED): # Only action available is loiter.
                pass
            elif (uav_location == UAVLocation.BASE_LOC):
                if(uav_fuel == self.FULL_FUEL): # Without full fuel, uav cannot leave base
                    uav_actions.append(UAVAction.ADVANCE)
            elif (uav_location == UAVLocation.SURVEIL_LOC):
                uav_actions.append(UAVAction.RETREAT)
            else: # uav_location is in one of the communications regions
                uav_actions.append(UAVAction.ADVANCE)
                uav_actions.append(UAVAction.RETREAT)
            if(isinstance(uav_actions,int)):
                validActions.append([uav_actions])
            else:
                validActions.append(uav_actions)
        print validActions
        return self.vecList2id(validActions, UAVAction.SIZE) # TODO place this in tools
    
            # Given a list of lists 'validActions' of the form [[0,1,2],[0,1],[1,2],[0,1]]... return
        # unique id for each permutation between lists; eg above, would return 3*2*2*2 values
        # ranging from 0 to 3^4 -1 (3 is max value possible in each of the lists)
        # Takes parameters of totalActionSpaceSize, here 3^4-1, and number of actions available
        # to each agent, here 3
            
            ####### TODO place this in Tools
            # Given a list of lists of the form [[0,1,2],[0,1],[1,2],[0,1]]... return
            # unique id for each permutation between lists; eg above, would return 3*2*2*2 values
            # ranging from 0 to 3^4 -1 (3 is max value possible in each of the lists, maxValue)
    def vecList2id(self,x,maxValue):
    #returns a list of unique id's based on possible permutations of this list of lists
        _id = 0
        actionIDs = []
        curActionList = []
        limits = tile(maxValue, (1,len(x)))[0] # eg [3,3,3,3] # TODO redundant computation
        self.vecList2idHelper(x,actionIDs,0, curActionList, maxValue,limits) # TODO remove self
        
        return actionIDs
        
    def vecList2idHelper(self,x,actionIDs,ind,curActionList, maxValue,limits):
    #returns a list of unique id's based on possible permutations of this list of lists.  See vecList2id
        for curAction in x[ind]: # x[ind] is one of the lists, e.g [0, 2] or [1,2]
            partialActionAssignment = curActionList[:]
            partialActionAssignment.append(curAction)
            if(ind == len(x) - 1): # We have reached the final list, assignment is complete
#                print partialActionAssignment,',,',limits
                actionIDs.append(vec2id(partialActionAssignment, limits)) # eg [0,1,0,2] and [3,3,3,3]
            else:
                self.vecList2idHelper(x,actionIDs,ind+1,partialActionAssignment, maxValue,limits) # TODO remove self
#        return actionIDs
    
if __name__ == '__main__':
        random.seed(0)
        p = PST();
        p.test(100)
        
        
        
    
