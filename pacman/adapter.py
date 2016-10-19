#!/usr/bin/env python
#  -*- coding: utf-8 -*-
"""
Adapts communication between controller and the Berkeley Pac-man simulator.
"""


import argparse
import os
import pickle
import random

from berkeley.game import Agent as BerkeleyGameAgent, Directions
from berkeley.graphicsDisplay import PacmanGraphics as BerkeleyGraphics
from berkeley.layout import getLayout as get_berkeley_layout
from berkeley.pacman import runGames as run_berkeley_games
from berkeley.textDisplay import NullGraphics as BerkeleyNullGraphics

import agents
import messages

# @todo properly include communication module from parent folder
import sys
sys.path.insert(0, '..')
import communication
import core

__author__ = "Matheus Portela and Guilherme N. Ramos"
__credits__ = ["Matheus Portela", "Guilherme N. Ramos", "Renato Nobre",
               "Pedro Saman"]
__maintainer__ = "Guilherme N. Ramos"
__email__ = "gnramos@unb.br"


# Default settings (CLI parsing)
DEFAULT_GHOST_AGENT = 'ai'
DEFAULT_LAYOUT = 'classic'
DEFAULT_NUMBER_OF_GHOSTS = 3
DEFAULT_NUMBER_OF_LEARNING_RUNS = 100
DEFAULT_NUMBER_OF_TEST_RUNS = 15
DEFAULT_PACMAN_AGENT = 'random'
DEFAULT_NOISE = 0

# Pac-Man game configuration
NUMBER_OF_BERKELEY_GAMES = 1
RECORD_BERKELEY_GAMES = False


def log(msg):
    print '[  Adapter ] {}'.format(msg)


# @todo Parse arguments outside class, pass values as arguments for
# constructor.
class BerkeleyAdapter(core.BaseExperiment):
    # @todo define pacman-agent choices and ghost-agent choices from agents.py
    # file
    def __init__(self,
                 pacman_agent=DEFAULT_PACMAN_AGENT,
                 ghost_agent=DEFAULT_GHOST_AGENT,
                 num_ghosts=DEFAULT_NUMBER_OF_GHOSTS,
                 noise=DEFAULT_NOISE,
                 policy_file=None,
                 layout_map=DEFAULT_LAYOUT,
                 learn_runs=DEFAULT_NUMBER_OF_LEARNING_RUNS,
                 test_runs=DEFAULT_NUMBER_OF_TEST_RUNS,
                 output_file=None,
                 graphics=False,
                 context=None,
                 endpoint=None,
                 address=None,
                 port=None):

        # Layout ##############################################################
        LAYOUT_PATH = 'pacman/layouts'
        file_name = str(num_ghosts) + 'Ghosts'
        layout_file = '/'.join([LAYOUT_PATH, layout_map + file_name])
        self.layout = get_berkeley_layout(layout_file)
        if not self.layout:
            raise ValueError('Layout {} missing.'.format(layout_file))
        log('Loaded {}.'.format(layout_file))

        # Pac-Man #############################################################
        self.pacman = BerkeleyAdapterAgent(agent_type=pacman_agent)

        # Ghosts ##############################################################
        self.num_ghosts = int(num_ghosts)
        if not (1 <= self.num_ghosts <= 4):
            raise ValueError('Must 1-4 ghost(s).')

        if ghost_agent == 'random':
            self.ghost_class = agents.RandomGhost
        elif ghost_agent == 'ai':
            self.ghost_class = agents.BehaviorLearningGhostAgent
        else:
            raise ValueError('Ghost agent must be ai or random.')

        ghost_name = self.ghost_class.__name__
        self.ghosts = []
        for i in xrange(num_ghosts):
            if context and endpoint:
                client = communication.InprocClient(context, endpoint)
            else:
                client = communication.TCPClient(address, port)

            ghost = agents.GhostAdapterAgent(i + 1, client=client)
            log('Created {} #{}.'.format(ghost_name, ghost.agent_id))
            ghost.register('ghost', self.ghost_class)
            self.ghosts.append(ghost)

        self.all_agents = self.ghosts

        # Policies ############################################################
        self.policy_file = str(policy_file) if policy_file else None

        # Runs ################################################################
        self.learn_runs = int(learn_runs)
        assert self.learn_runs > 0

        self.test_runs = int(test_runs)
        assert self.test_runs > 0

        # Output ##############################################################
        if output_file:
            self.output_file = str(output_file)
        else:
            self.output_file = '{}_{}_{}_{}.res'.format(pacman_agent,
                                                        layout_map,
                                                        num_ghosts,
                                                        ghost_agent)

        # Graphical interface #################################################
        if graphics:
            self.display = BerkeleyGraphics()
        else:
            self.display = BerkeleyNullGraphics()

        log('Ready!')

    def _load_policies_from_file(self, filename):
        self.policies = {}

        if filename and os.path.isfile(filename):
            log('Loading policies from {}.'.format(filename))
            with open(filename) as f:
                self.policies = pickle.loads(f.read())

    def _log_behavior_count(self, agent):
        behavior_count = agent.get_behavior_count()

        for behavior, count in behavior_count.items():
            if behavior not in self.results['behavior_count'][agent.agent_id]:
                self.results['behavior_count'][agent.agent_id][behavior] = []
            self.results['behavior_count'][agent.agent_id][behavior].append(
                count)

    def _run_game(self):
        # Start new game
        for agent in self.all_agents:
            agent.start_game(self.layout)

        # Load policies to agents
        if self.policy_file:
            for agent in self.all_agents:
                if agent.agent_id in self.policies:
                    agent.load_policy(self.policies[agent.agent_id])

        log('Simulating game...')
        simulated_game = run_berkeley_games(self.layout, self.pacman,
                                            self.ghosts, self.display,
                                            NUMBER_OF_BERKELEY_GAMES,
                                            RECORD_BERKELEY_GAMES)[0]

        # Do this so as agents can receive the last reward
        self.pacman.getAction(simulated_game.state)
        for agent in self.all_agents:
            agent.update(simulated_game.state)

        # Log behavior count
        if self.ghost_class == agents.BehaviorLearningGhostAgent:
            for ghost in self.ghosts:
                self._log_behavior_count(ghost)

        # Log score
        return simulated_game.state.getScore()

    def _save_policies(self):
        if self.pacman_class == agents.BehaviorLearningPacmanAgent:
            self.policies[self.pacman.agent_id] = self.pacman.policy

        if self.ghost_class == agents.BehaviorLearningGhostAgent:
            for ghost in self.ghosts:
                self.policies[ghost.agent_id] = ghost.get_policy()

        self._write_to_file(self.policy_file, self.policies)

    def _write_to_file(self, filename, content):
        log('Saving results to {}'.format(filename))
        with open(filename, 'w') as f:
            f.write(pickle.dumps(content))

    def start(self):
        log('Now running')

        self.results = {
            'learn_scores': [],
            'test_scores': [],
            'behavior_count': {},
        }

        if self.ghost_class == agents.BehaviorLearningGhostAgent:
            for ghost in self.ghosts:
                self.results['behavior_count'][ghost.agent_id] = {}

        # Load policies from file
        self._load_policies_from_file(self.policy_file)

        # Initialize agents
        for agent in self.all_agents:
            agent.initialize()

        self.pacman.policy = self.policies.get(self.pacman.agent_id, None)
        self.pacman.layout = self.layout
        self.pacman.start_experiment()

    def execute(self):
        for x in xrange(self.learn_runs):
            log('LEARN game {} (of {})'.format(x + 1, self.learn_runs))

            self.pacman.start_game()

            score = self._run_game()
            self.results['learn_scores'].append(score)

            self.pacman.results['scores'].append(score)
            self.pacman.finish_game()

        self.pacman.enable_test_mode()
        for agent in self.all_agents:
            agent.enable_test_mode()

        for x in xrange(self.test_runs):
            log('TEST game {} (of {})'.format(x + 1, self.test_runs))

            self.pacman.start_game()

            score = self._run_game()
            self.results['test_scores'].append(score)

            self.pacman.results['scores'].append(score)
            self.pacman.finish_game()

    def stop(self):
        self.pacman.finish_experiment()

        if self.policy_file:
            self._save_policies()

        log('Learn scores: {}'.format(self.results['learn_scores']))
        log('Test scores: {}'.format(self.results['test_scores']))

        self._write_to_file(self.output_file, self.results)


class BerkeleyAdapterAgent(core.BaseAdapterAgent, BerkeleyGameAgent):
    pacman_index = 0
    noise = 0

    def __init__(self, agent_type='random', *args, **kwargs):
        core.BaseAdapterAgent.__init__(self, *args, **kwargs)
        BerkeleyGameAgent.__init__(self, 0)
        self.agent_type = agent_type
        self.agent_class = None
        self.policy = None
        self.game_state = None
        self.is_test_mode = False
        self.layout = None
        self.results = {
            'scores': [],
            'behavior_count': {},
        }

    # BerkeleyGameAgent required methods

    @property
    def agent_id(self):
        return self.index  # from BerkeleyGameAgent

    def getAction(self, game_state):
        """Returns a legal action (from Directions)."""
        self.game_state = game_state
        action = self.receive_action()
        self.previous_action = action
        return action

    # BaseAdapterAgent required methods

    def start_experiment(self):
        log('[BerkeleyAdapterAgent] Start experiment')
        self._load_policy()
        self._register()
        self._initialize()

    def _load_policy(self):
        log('[BerkeleyAdapterAgent] Loading policies')
        if self.policy:
            message = messages.PolicyMessage(policy)
            self.communicate(message)

    def _register(self):
        log('[BerkeleyAdapterAgent] Register {}/{}'.format(
            'pacman', self.agent_type))

        if self.agent_type == 'random':
            self.agent_class = agents.RandomPacmanAgent
        elif self.agent_type == 'random2':
            self.agent_class = agents.RandomPacmanAgentTwo
        elif self.agent_type == 'ai':
            self.agent_class = agents.BehaviorLearningPacmanAgent
        elif self.agent_type == 'eater':
            self.agent_class = agents.EaterPacmanAgent
        else:
            raise ValueError('Pac-Man agent must be ai, random, random2 or '
                             'eater.')

        message = messages.RequestRegisterMessage(
            self.agent_id, 'pacman', self.agent_class)
        self.communicate(message)

    def _initialize(self):
        log('[BerkeleyAdapterAgent] Initialize agent')
        message = messages.RequestInitializationMessage(self.agent_id)
        self.communicate(message)

    def finish_experiment(self):
        log('[BerkeleyAdapterAgent] Finish experiment')
        log('[BerkeleyAdapterAgent] Scores: {}'.format(self.results['scores']))

    def start_game(self):
        log('[BerkeleyAdapterAgent] Start game')
        self._reset_game_data()
        self._request_game_start()

    def _reset_game_data(self):
        self.previous_score = 0
        self.previous_action = Directions.NORTH

    def _request_game_start(self):
        log('[BerkeleyAdapterAgent] Request game start')
        message = messages.RequestGameStartMessage(
            agent_id=self.agent_id,
            map_width=self.layout.width,
            map_height=self.layout.height)
        self.communicate(message)

    def finish_game(self):
        log('[BerkeleyAdapterAgent] Finish game')
        log('[BerkeleyAdapterAgent] Scores: {}'.format(self.results['scores'][-1]))

        if self.agent_type == 'ai':
            self._log_behavior_count()

    def _log_behavior_count(self):
        log('[BerkeleyAdapterAgent] Log behavior count')
        self._log_behavior_count(self.pacman)

        message = messages.RequestBehaviorCountMessage(self.agent_id)
        reply_message = self.communicate(message)
        behavior_count = reply_message.count

        for behavior, count in behavior_count.items():
            if behavior not in self.results['behavior_count'][agent.agent_id]:
                self.results['behavior_count'][agent.agent_id][behavior] = []
            self.results['behavior_count'][agent.agent_id][behavior].append(
                count)

    def send_state(self):
        log('[BerkeleyAdapterAgent] Send state')

        agent_positions = {}

        agent_positions[BerkeleyAdapterAgent.pacman_index] = (
            self.game_state.getPacmanPosition()[::-1])

        for id_, pos in enumerate(self.game_state.getGhostPositions()):
            pos_y = pos[::-1][0] + self._noise_error()
            pos_x = pos[::-1][1] + self._noise_error()
            agent_positions[id_ + 1] = (pos_y, pos_x)

        food_positions = []
        for x, row in enumerate(self.game_state.getFood()):
            for y, is_food in enumerate(row):
                if is_food:
                    food_positions.append((y, x))

        fragile_agents = {}
        for id_, s in enumerate(self.game_state.data.agentStates):
            fragile_agents[id_] = 1.0 if s.scaredTimer > 0 else 0.0

        wall_positions = []
        for x, row in enumerate(self.game_state.getWalls()):
            for y, is_wall in enumerate(row):
                if is_wall:
                    wall_positions.append((y, x))

        reward = self._calculate_reward(self.game_state.getScore())
        self.previous_score = self.game_state.getScore()

        message = messages.StateMessage(
            agent_id=self.agent_id,
            agent_positions=agent_positions,
            food_positions=food_positions,
            fragile_agents=fragile_agents,
            wall_positions=wall_positions,
            legal_actions=self.game_state.getLegalActions(self.agent_id),
            reward=reward,
            executed_action=self.previous_action,
            test_mode=self.is_test_mode)

        return self.communicate(message)

    def _noise_error(self):
        return random.randrange(-BerkeleyAdapterAgent.noise,
                                BerkeleyAdapterAgent.noise + 1)

    def receive_action(self):
        log('[BerkeleyAdapterAgent] Receive action')
        action_message = self.send_state()
        return action_message.action

    def send_reward(self):
        log('[BerkeleyAdapterAgent] Send reward')
        pass

    def _calculate_reward(self, current_score):
        return current_score - self.previous_score

    def enable_test_mode(self):
        log('[BerkeleyAdapterAgent] Enable test mode')
        self.is_test_mode = True


def build_adapter(context=None, endpoint=None,
                  address=communication.DEFAULT_CLIENT_ADDRESS,
                  port=communication.DEFAULT_TCP_PORT,
                  **kwargs):
    if context and endpoint:
        log('Connecting with inproc communication')
        adapter = BerkeleyAdapter(context=context, endpoint=endpoint, **kwargs)
    else:
        log('Connecting with TCP communication (address {}, port {})'.format(
            address, port))
        adapter = BerkeleyAdapter(address=address, port=port, **kwargs)

    return adapter

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Run Pac-Man simulator adapter system.')
    parser.add_argument('-g', '--graphics', dest='graphics', default=False,
                        action='store_true',
                        help='display graphical user interface')
    parser.add_argument('-o', '--output', dest='output_file', type=str,
                        help='results output file')

    group = parser.add_argument_group('Experiment Setup')
    group.add_argument('--ghost-agent', dest='ghost_agent', type=str,
                       choices=['random', 'ai'], default=DEFAULT_GHOST_AGENT,
                       help='select ghost agent')
    group.add_argument('-l', '--learn-num', dest='learn_runs', type=int,
                       default=DEFAULT_NUMBER_OF_LEARNING_RUNS,
                       help='number of games to learn from')
    group.add_argument('--layout', dest='layout', type=str,
                       default=DEFAULT_LAYOUT, choices=['classic', 'medium'],
                       help='Game layout')
    group.add_argument('--noise', dest='noise', type=int,
                       default=DEFAULT_NOISE,
                       help='introduce noise in position measurements')
    group.add_argument('--num-ghosts', dest='num_ghosts',
                       type=int, choices=range(1, 5),
                       default=DEFAULT_NUMBER_OF_GHOSTS,
                       help='number of ghosts in game')
    group.add_argument('--pacman-agent', dest='pacman_agent', type=str,
                       choices=['random', 'random2', 'ai', 'eater'],
                       default=DEFAULT_PACMAN_AGENT,
                       help='select Pac-Man agent')
    group.add_argument('--policy-file', dest='policy_file',
                       type=lambda s: unicode(s, 'utf8'),
                       help='load and save Pac-Man policy from the given file')
    group.add_argument('-t', '--test-num', dest='test_runs', type=int,
                       default=DEFAULT_NUMBER_OF_TEST_RUNS,
                       help='number of games to test learned policy')

    group = parser.add_argument_group('Communication')
    group.add_argument('--addr', dest='address', type=str,
                       default=communication.DEFAULT_CLIENT_ADDRESS,
                       help='Client address to connect to adapter (TCP '
                            'connection)')
    group.add_argument('--port', dest='port', type=int,
                       default=communication.DEFAULT_TCP_PORT,
                       help='Port to connect to controller (TCP connection)')

    args, unknown = parser.parse_known_args()

    adapter = build_adapter(
        address=communication.DEFAULT_CLIENT_ADDRESS,
        port=communication.DEFAULT_TCP_PORT,
        pacman_agent=args.pacman_agent,
        ghost_agent=args.ghost_agent,
        num_ghosts=args.num_ghosts,
        noise=args.noise,
        policy_file=args.policy_file,
        layout_map=args.layout,
        learn_runs=args.learn_runs,
        test_runs=args.test_runs,
        output_file=args.output_file,
        graphics=args.graphics)

    try:
        adapter.run()
    except KeyboardInterrupt:
        print '\n\nInterrupted execution\n'
