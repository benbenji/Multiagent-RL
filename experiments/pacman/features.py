#  -*- coding: utf-8 -*-
"""Features to extract high-level information from simulation state."""


class Feature(object):
    """Defines a representation of the current status of a variable in the
    simulated environment.
    """
    def __call__(self, state):
        raise NotImplementedError('Feature must implement __call__')


# Q-learning with function approximation requires features to be extracted from
# an estimated state of the system. Therefore, two features were implemented
# here:
# - Distance from each agent, using accessibility graph to deal with obstacles
# in the environment;
# - Indicator whether Pac-Man captured a capsule, hence, being able to capture
# the ghost.


class XPositionFeature(Feature):
    def __call__(self, state):
        agent_position = state.get_position()
        return agent_position[1]


class YPositionFeature(Feature):
    def __call__(self, state):
        agent_position = state.get_position()
        return agent_position[0]


class EnemyDistanceFeature(Feature):
    """Defines the distance to an enemy."""
    def __init__(self, enemy_id):
        self.enemy_id = enemy_id

    def __call__(self, state):
        agent_position = state.get_position()
        enemy_position = state.get_agent_position(self.enemy_id)
        distance = state.calculate_distance(agent_position, enemy_position)

        if distance == 0.0:
            distance = 1.0

        return (1.0 / distance)


class FoodDistanceFeature(Feature):
    def __call__(self, state):
        distance = state.get_food_distance()

        if distance == 0.0:
            distance = 1.0

        return (1.0 / distance)


class FragileAgentFeature(Feature):
    """Indicates the probability that the Pac-Man is able to capture the ghosts
    or not.
    """
    def __init__(self, agent_id):
        self.agent_id = agent_id

    def __call__(self, state):
        return state.get_fragile_agent(self.agent_id)
