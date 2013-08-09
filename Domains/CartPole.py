#Copyright (c) 2013, Alborz Geramifard, Robert H. Klein, and Jonathan P. How
#All rights reserved.

#Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:

#Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.

#Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

#Neither the name of ACL nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.

#THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

#Locate RLPy
#================
from Domain import Domain
import numpy as np
import scipy.integrate
from Tools import pl, mpatches, mpath, fromAtoB, lines, rk4, wrap, bound, colors
#from scipy import integrate # for integration of state

#########################################################
# \author Robert H Klein, Alborz Geramifard at MIT, Dec. 6 2012
#########################################################
#
# State: [theta, thetaDot, x, xDot].
# Actions: [-50, 0, 50]
#
# theta    = Angular position of pendulum
# (relative to straight up at 0 rad),and positive clockwise. \n
# thetaDot = Angular rate of pendulum \n
# x        = Linear position of the cart on its track (positive right). \n
# xDot     = Linear velocity of the cart on its track.
#
# Actions take the form of force applied to cart; \n
# [-50, 0, 50] N force are the default available actions. \n
# Positive force acts to the right on the cart.
#
# Uniformly distributed noise is added with magnitude 10 N.
#
# Per Lagoudakis and Parr 2003, derived from Wang 1996.
# (See "1Link" implementation by L & P.)
# Dynamics in x, xdot derived from CartPole implementation
# of rl-community.org, from Sutton and Barto's Pole-balancing
# task in <Reinforcement Learning: An Introduction> (1998)
# (See CartPole implementation in the RL Community,
# http://library.rl-community.org/wiki/CartPole)
######################################################


## @todo: can eliminate an entire dimension of the state space, xdot.
# However, must internally keep track of it for use in dynamics.
# RL_Glue and RL Community use the full 4-state system.

class CartPole(Domain):

    # Domain constants per RL Community / RL_Glue CartPole implementation.
    # (http://code.google.com/p/rl-library/wiki/CartpoleJava)
    ## Newtons, N - Torque values available as actions [-50,0,50 per DPF]
    AVAIL_FORCE         = np.array([-10, 10])
    ## kilograms, kg - Mass of the pendulum arm
    MASS_PEND           = 0.1
    ## kilograms, kg - Mass of cart
    MASS_CART           = 1.0
    ## meters, m - Physical length of the pendulum, meters (note the moment-arm lies at half this distance)
    LENGTH              = 1.0
    ## m/s^2 - gravitational constant
    ACCEL_G             = 9.8
    ## Time between steps
    dt                  = 0.02
    ## Newtons, N - Maximum noise possible, uniformly distributed
    force_noise_max     = 0.

    #: integration type, can be 'rk4', 'odeint' or 'euler'
    int_type = 'euler'

    #: number of steps for Euler integration
    num_euler_steps = 1

    ## Limits on pendulum rate [per RL Community CartPole]
    ANGULAR_RATE_LIMITS = [-6.0, 6.0]
    ## Reward received on each step the pendulum is in the goal region
    GOAL_REWARD         = 1
    ## m - Limits on cart position [Per RL Community CartPole]
    POSITON_LIMITS      = [-2.4, 2.4]
    ## m/s - Limits on cart velocity [per RL Community CartPole]
    VELOCITY_LIMITS     = [-6.0, 6.0]

    # Domain constants

    ## Max number of steps per trajectory
    episodeCap          = 3000
    ## Set to non-zero to enable print statements
    DEBUG               = 0

    ## Domain constants computed in __init__. \n
    # m - Length of the moment-arm to the center of mass, equal to half the pendulum length
    MOMENT_ARM          = 0
    # Note that some elsewhere refer to this simply as 'length' somewhat of a misnomer.
    ## 1/kg - Used in dynamics computations, equal to 1 / (MASS_PEND + MASS_CART)
    _ALPHA_MASS         = 0

    # Plotting variables
    pendulumArm = None
    cartBox = None
    actionArrow = None
    ACTION_ARROW_LENGTH = 0.4
    domainFig = None
    circle_radius = 0.05
    PENDULUM_PIVOT_Y = 0  # Y position of pendulum pivot
    RECT_WIDTH = 0.5
    RECT_HEIGHT = .4
    BLOB_WIDTH = RECT_HEIGHT / 2.0
    PEND_WIDTH = 2
    GROUND_WIDTH = 2
    GROUND_HEIGHT = 1

    #Visual Stuff
    valueFunction_fig       = None
    policy_fig              = None
    MIN_RETURN              = None  # Minimum return possible, used for graphical normalization, computed in init
    MAX_RETURN              = None  # Minimum return possible, used for graphical normalization, computed in init
    circle_radius           = 0.05
    ARM_LENGTH              = 1.0
    PENDULUM_PIVOT_X        = 0  # X position is also fixed in this visualization
    PENDULUM_PIVOT_Y        = 0  # Y position of pendulum pivot
    pendulumArm             = None
    pendulumBob             = None
    actionArrow             = None
    domain_fig              = None
    Theta_discretization    = 20  # Used for visualizing the policy and the value function
    ThetaDot_discretization = 20  # Used for visualizing the policy and the value function

    # are constrained by the format expected by ode functions.
    def __init__(self, logger=None):
        # Limits of each dimension of the state space. Each row corresponds to one dimension and has two elements [min, max]
        #        self.states_num = inf       # Number of states
        self.actions_num        = len(self.AVAIL_FORCE)      # Number of Actions
        self.continuous_dims    = [StateIndex.THETA, StateIndex.THETA_DOT, StateIndex.X, StateIndex.X_DOT]

        self.MOMENT_ARM         = self.LENGTH / 2.0
        self._ALPHA_MASS        = 1.0 / (self.MASS_CART + self.MASS_PEND)
        self.DimNames           = ['Theta', 'Thetadot', 'X', 'Xdot']

        if self.logger:
            self.logger.log("length:\t\t%0.2f(m)" % self.LENGTH)
            self.logger.log("dt:\t\t\t%0.2f(s)" % self.dt)
        self._assignGroundVerts()
        super(CartPole, self).__init__(logger)

    def showDomain(self, s, a=0):
        ## Plot the pendulum and its angle, along with an arc-arrow indicating the
        # direction of torque applied (not including noise!)
        # Pendulum rotation is centered at origin

        if self.domainFig is None:  # Need to initialize the figure
            self.domainFig = pl.figure("Domain")
            ax = self.domainFig.add_axes([0, 0, 1, 1], frameon=True, aspect=1.)
            self.pendulumArm = lines.Line2D([], [], linewidth = self.PEND_WIDTH, color='black')
            self.cartBox    = mpatches.Rectangle([0, self.PENDULUM_PIVOT_Y - self.RECT_HEIGHT / 2.0], self.RECT_WIDTH, self.RECT_HEIGHT, alpha=.4)
            self.cartBlob   = mpatches.Rectangle([0, self.PENDULUM_PIVOT_Y - self.BLOB_WIDTH / 2.0], self.BLOB_WIDTH, self.BLOB_WIDTH, alpha=.4)
            ax.add_patch(self.cartBox)
            ax.add_line(self.pendulumArm)
            ax.add_patch(self.cartBlob)
            #Draw Ground
            path    = mpath.Path(self.GROUND_VERTS)
            patch   = mpatches.PathPatch(path,hatch="//")
            ax.add_patch(patch)
            self.timeText = ax.text(self.POSITON_LIMITS[1], self.LENGTH,"")
            self.rewardText = ax.text(self.POSITON_LIMITS[0], self.LENGTH,"")
            # Allow room for pendulum to swing without getting cut off on graph
            viewableDistance = self.LENGTH + self.circle_radius + 0.5
            ax.set_xlim(self.POSITON_LIMITS[0] - viewableDistance, self.POSITON_LIMITS[1] + viewableDistance)
            ax.set_ylim(-viewableDistance, viewableDistance)
            #ax.set_aspect('equal')

            pl.show()

        self.domainFig = pl.figure("Domain")
        forceAction = self.AVAIL_FORCE[a]
        curX = s[StateIndex.X]
        curTheta = s[StateIndex.THETA]

        pendulumBobX = curX + self.LENGTH  * np.sin(curTheta)
        pendulumBobY = self.PENDULUM_PIVOT_Y + self.LENGTH * np.cos(curTheta)

        if self.isTerminal(s):
            t = 1.
            self.timeText.set_text("{0:.2f}s".format(t * self.dt, pendulumBobX, pendulumBobY))
        r = self._getReward(s, a)
        self.rewardText.set_text("Reward {0:g}".format(r, pendulumBobX, pendulumBobY))
        if self.DEBUG: print 'Pendulum Position: ',pendulumBobX,pendulumBobY

        # update pendulum arm on figure
        self.pendulumArm.set_data([curX, pendulumBobX],[self.PENDULUM_PIVOT_Y, pendulumBobY])
        self.cartBox.set_x(curX - self.RECT_WIDTH/2.0)
        self.cartBlob.set_x(curX - self.BLOB_WIDTH/2.0)


        if self.actionArrow is not None:
            self.actionArrow.remove()
            self.actionArrow = None

        if forceAction == 0: pass # no force
        else:  # cw or ccw torque
            if forceAction > 0: # rightward force
                 self.actionArrow = fromAtoB(
                    curX - self.ACTION_ARROW_LENGTH - self.RECT_WIDTH/2.0, 0,
                    curX - self.RECT_WIDTH/2.0,  0,
                    'k',"arc3,rad=0",
                    0,0, 'simple'
                )
            else:# leftward force
                self.actionArrow = fromAtoB(
                    curX + self.ACTION_ARROW_LENGTH + self.RECT_WIDTH/2.0, 0,
                    curX + self.RECT_WIDTH/2.0, 0,
                    'r',"arc3,rad=0",
                    0,0,'simple'
                )

        pl.draw()
        #        sleep(self.dt)


    def s0(self):
        # Defined by children
        pass

    def possibleActions(self,s): # Return list of all indices corresponding to actions available
        return np.arange(self.actions_num)

    def step(self, a):
        # Simulate one step of the CartPole after taking action a
        # Note that at present, this is almost identical to the step for the Pendulum.

        forceAction = self.AVAIL_FORCE[a]

        # Add noise to the force action
        if self.force_noise_max > 0:
            forceAction += np.random.uniform(-self.force_noise_max, self.force_noise_max)

        # Now, augment the state with our force action so it can be passed to _dsdt
        s_augmented = np.append(self.state, forceAction)
        if self.int_type == "euler":
            int_fun = self.euler_int
        elif self.int_type == "odeint":
            int_fun = scipy.integrate.odeint
        else:
            int_fun = rk4
        ns = int_fun(self._dsdt, s_augmented, [0, self.dt])
        ns = ns[-1]  # only care about final timestep of integration returned by integrator

        ns = ns[0:4]  # [theta, thetadot, x, xDot]
        # ODEINT IS TOO SLOW!
        # ns_continuous = integrate.odeint(self._dsdt, self.s_continuous, [0, self.dt])
        #self.s_continuous = ns_continuous[-1] # We only care about the state at the ''final timestep'', self.dt

        theta                   = wrap(ns[StateIndex.THETA], -np.pi, np.pi)
        ns[StateIndex.THETA]    = bound(theta, self.ANGLE_LIMITS[0], self.ANGLE_LIMITS[1])
        ns[StateIndex.THETA_DOT]= bound(ns[StateIndex.THETA_DOT], self.ANGULAR_RATE_LIMITS[0], self.ANGULAR_RATE_LIMITS[1])
        ns[StateIndex.X]        = bound(ns[StateIndex.X], self.POSITON_LIMITS[0], self.POSITON_LIMITS[1])
        ns[StateIndex.X_DOT]    = bound(ns[StateIndex.X_DOT], self.VELOCITY_LIMITS[0], self.VELOCITY_LIMITS[1])
        terminal                    = self.isTerminal(ns)
        reward                      = self._getReward(ns, a)
        self.state = ns.copy()
        return reward, ns, terminal

    def euler_int(self, df, x0, times):
        """
        performs Euler integration with interface similar to other methods.
        BEWARE: times argument ignored
        """
        steps = self.num_euler_steps
        dt = float(times[-1])
        ns = x0.copy()
        for i in range(steps):
            ns += dt / steps * df(ns, i * dt / steps)
        return [ns]


    ## From CartPole implementation described in class definition, from rlcommunity.org
    # (http://library.rl-community.org/wiki/CartPole)
    # Used by odeint to numerically integrate the differential equation
    def _dsdt(self, s_augmented, t):
        # This function is needed for ode integration.  It calculates and returns the
        # derivatives at a given state, s.  The last element of s_augmented is the
        # force action taken, required to compute these derivatives.
        #
        # ThetaDotDot =
        #
        #     g sin(theta) - (alpha)ml(tdot)^2 * sin(2theta)/2  -  (alpha)cos(theta)u
        #     -----------------------------------------------------------------------
        #                           4l/3  -  (alpha)ml*cos^2(theta)
        #
        #         g sin(theta) - w cos(theta)
        #   =     ---------------------------
        #         4l/3 - (alpha)ml*cos^2(theta)
        #
        # where w = (alpha)u + (alpha)ml*(tdot)^2*sin(theta)
        # Note we use the trigonometric identity sin(2theta)/2 = cos(theta)*sin(theta)
        #
        # xDotDot = w - (alpha)ml * thetaDotDot * cos(theta)

        g = self.ACCEL_G
        l = self.MOMENT_ARM
        m_pendAlphaTimesL = self.MASS_PEND * self._ALPHA_MASS * l
        theta       = s_augmented[StateIndex.THETA]
        thetaDot    = s_augmented[StateIndex.THETA_DOT]
        xDot        = s_augmented[StateIndex.X_DOT]
        force       = s_augmented[StateIndex.FORCE]

        sinTheta = np.sin(theta)
        cosTheta = np.cos(theta)
        thetaDotSq = thetaDot ** 2

        term1 = force*self._ALPHA_MASS + m_pendAlphaTimesL * thetaDotSq * sinTheta
        numer = g * sinTheta - cosTheta * term1
        denom = 4.0 * l / 3.0  -  m_pendAlphaTimesL * (cosTheta ** 2)
        # g sin(theta) - (alpha)ml(tdot)^2 * sin(2theta)/2  -  (alpha)cos(theta)u
        # -----------------------------------------------------------------------
        #                     4l/3  -  (alpha)ml*cos^2(theta)
        thetaDotDot = numer / denom

        xDotDot = term1 - m_pendAlphaTimesL * thetaDotDot * cosTheta
        return np.array((thetaDot, thetaDotDot, xDot, xDotDot, 0))  # final cell corresponds to action passed in

    ## @param s: state
    #  @param a: action
    ## @return: Reward earned for this state-action pair.
    def _getReward(self, s, a):
        # Return the reward earned for this state-action pair
        abstract

    ## Assigns the GROUND_VERTS array, placed here to avoid cluttered code in init.
    def _assignGroundVerts(self):
        minPosition = self.POSITON_LIMITS[0]-self.RECT_WIDTH/2.0
        maxPosition = self.POSITON_LIMITS[1]+self.RECT_WIDTH/2.0
        self.GROUND_VERTS = np.array([
            (minPosition, -self.RECT_HEIGHT / 2.0),
            (minPosition,self.RECT_HEIGHT / 2.0),
            (minPosition-self.GROUND_WIDTH, self.RECT_HEIGHT/2.0),
            (minPosition-self.GROUND_WIDTH, self.RECT_HEIGHT/2.0-self.GROUND_HEIGHT),
            (maxPosition+self.GROUND_WIDTH, self.RECT_HEIGHT/2.0-self.GROUND_HEIGHT),
            (maxPosition+self.GROUND_WIDTH, self.RECT_HEIGHT/2.0),
            (maxPosition, self.RECT_HEIGHT/2.0),
            (maxPosition, -self.RECT_HEIGHT/2.0),
        ])

    def showLearning(self, representation):
        """
        visualizes the policy and value function for the the cart being at the
        center with 0 velocity
        """
        granularity = 5.
        pi = np.zeros((self.Theta_discretization*granularity, self.ThetaDot_discretization*granularity),'uint8')
        V = np.zeros((self.Theta_discretization*granularity,self.ThetaDot_discretization*granularity))

        if self.valueFunction_fig is None:
            self.valueFunction_fig   = pl.figure("Value Function")
            self.valueFunction_fig   = pl.imshow(V, cmap='ValueFunction',interpolation='nearest',origin='lower',vmin=self.MIN_RETURN,vmax=self.MAX_RETURN)
            #pl.xticks(self.xTicks,self.xTicksLabels, fontsize=12)
            #pl.yticks(self.yTicks,self.yTicksLabels, fontsize=12)
            pl.xlabel(r"$\theta$ (degree)")
            pl.ylabel(r"$\dot{\theta}$ (degree/sec)")
            pl.title('Value Function')

            self.policy_fig = pl.figure("Policy")
            self.policy_fig = pl.imshow(pi, cmap='InvertedPendulumActions', interpolation='nearest',origin='lower',vmin=0,vmax=self.actions_num)
            #pl.xticks(self.xTicks,self.xTicksLabels, fontsize=12)
            #pl.yticks(self.yTicks,self.yTicksLabels, fontsize=12)
            pl.xlabel(r"$\theta$ (degree)")
            pl.ylabel(r"$\dot{\theta}$ (degree/sec)")
            pl.title('Policy')
            pl.show()
            f = pl.gcf()
            f.subplots_adjust(left=0,wspace=.5)

        # Create the center of the grid cells both in theta and thetadot_dimension
        theta_binWidth      = (self.ANGLE_LIMITS[1]-self.ANGLE_LIMITS[0])/(self.Theta_discretization*granularity)
        thetas              = np.linspace(self.ANGLE_LIMITS[0]+theta_binWidth/2, self.ANGLE_LIMITS[1]-theta_binWidth/2, self.Theta_discretization*granularity)
        theta_dot_binWidth  = (self.ANGULAR_RATE_LIMITS[1]-self.ANGULAR_RATE_LIMITS[0])/(self.ThetaDot_discretization*granularity)
        theta_dots          = np.linspace(self.ANGULAR_RATE_LIMITS[0]+theta_dot_binWidth/2, self.ANGULAR_RATE_LIMITS[1]-theta_dot_binWidth/2, self.ThetaDot_discretization*granularity)
        for row, thetaDot in enumerate(theta_dots):
            for col, theta in enumerate(thetas):
                s           = np.array([theta,thetaDot, 0, 0])
                Qs,As       = representation.Qs(s)
                pi[row,col] = As[np.argmax(Qs)]
                V[row,col]  = max(Qs)

        norm = colors.Normalize(vmin=V.min(), vmax=V.max())
        self.valueFunction_fig.set_data(V)
        self.valueFunction_fig.set_norm(norm)
        self.policy_fig.set_data(pi)
        pl.figure("Policy")
        pl.draw()
        pl.figure("Value Function")
        pl.draw()

# Flexible way to index states in the CartPole Domain.
#
# This class enumerates the different indices used when indexing the state. \n
# e.g. s[StateIndex.THETA] is guaranteed to return the angle state.
class StateIndex:
    THETA, THETA_DOT = 0,1
    X, X_DOT = 2,3
    FORCE = 4


class CartPoleBalanceOriginal(CartPole):
    """
    taken from
    http://webdocs.cs.ualberta.ca/~sutton/book/code/pole.c
    """
    ANGLE_LIMITS        = [-np.pi/15.0, np.pi/15.0]
    ANGULAR_RATE_LIMITS = [-2.0, 2.0]
    gamma               = .95
    AVAIL_FORCE         = np.array([-10, 10])
    int_type = "euler"
    num_euler_steps = 1

    def __init__(self, logger=None, good_reward=0.):
        self.good_reward = good_reward
        self.statespace_limits  = np.array([self.ANGLE_LIMITS, self.ANGULAR_RATE_LIMITS, self.POSITON_LIMITS, self.VELOCITY_LIMITS])
        self.state_space_dims = len(self.statespace_limits)
        super(CartPoleBalanceOriginal, self).__init__(logger)

    def s0(self):
        self.state = np.zeros(4)
        return self.state.copy()

    def _getReward(self, s, a):
        return self.good_reward if not self.isTerminal(s) else -1.

    def isTerminal(self, s):
        return (not (-np.pi/15 < s[StateIndex.THETA] < np.pi/15) or
                not (-2.4    < s[StateIndex.X]     < 2.4))


class CartPoleBalanceModern(CartPole):
    """
    more realistic version of balancing with 3 actions and some uinform noise
    """
    int_type = 'rk4'
    AVAIL_FORCE = np.array([-10., 0., 10.])
    force_noise_max = 1.
    gamma = .95
    int_type = "euler"
    num_euler_steps = 1
    ANGLE_LIMITS        = [-np.pi/15.0, np.pi/15.0]
    ANGULAR_RATE_LIMITS = [-2.0, 2.0]

    def __init__(self, logger=None):
        self.statespace_limits  = np.array([self.ANGLE_LIMITS, self.ANGULAR_RATE_LIMITS, self.POSITON_LIMITS, self.VELOCITY_LIMITS])
        self.state_space_dims = len(self.statespace_limits)
        super(CartPoleBalanceModern, self).__init__(logger)

    def s0(self):
        self.state = np.array([np.random.randn()*0.01, 0., 0., 0.])
        return self.state.copy()

    def _getReward(self, s, a):
        return 0. if not self.isTerminal(s) else -1.

    def isTerminal(self, s):
        return (not (-np.pi/15 < s[StateIndex.THETA] < np.pi/15) or
                not (-2.4    < s[StateIndex.X]     < 2.4))
