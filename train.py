import argparse
import ConfigureEnv
import os.path as osp
from dqn_utils import *
from gym import wrappers
from ConfigureEnv import *
from atari_wrappers import *
import torch.multiprocessing as mp
#
# Parse the input arguments.
def getInputArgs():
    parser = argparse.ArgumentParser('Configuration options.')
    parser.add_argument('--useTB', dest='useTB', default=False, action='store_true', help='Whether or not to log to Tesnor board.')
    parser.add_argument('--config', dest='configStr', default='DefaultConfig', type=str, help='Name of the config file to import.')
    parser.add_argument('--seed', dest='seed', default=1, help='Random seed.')
    args = parser.parse_args()
    return args
#
# Get the configuration, override as needed.
def getConfig(args):
    config_module = __import__('config.' + args.configStr)
    configuration = getattr(config_module, args.configStr)
    conf = configuration.Config(args.seed)
    #
    # Modifications to the configuration happen here.
    conf.useTensorBoard = args.useTB
    return conf
# 
# Setup learning.
def atari_learn(args):
    # explorer = Exploration.EpsilonGreedy(explorationSched, TensorConfig.TensorConfig(), replay_buffer, env, model)
    # parallelCfg = Exploration.ExploreParallelCfg()
    # parallelCfg.model = model
    # parallelCfg.exploreSched = explorationSched
    # parallelCfg.numFramesInBuffer = args.replaySize
    # explorer = Exploration.ParallelExplorer(parallelCfg)
    # print('Set seeds!')
    # setRandomSeeds(seed)
    conf = getConfig(args)
    #
    # Learn.
    import dqn
    dqn.learn(conf)

def setRandomSeeds(seed):
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)

def main():
    args = getInputArgs()
    #
    # The learning fn.
    atari_learn(args = args)

if __name__ == "__main__":
    mp.set_start_method('forkserver')
    main()
