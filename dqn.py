import sys
import copy
import random
import itertools
import gym.spaces
import numpy as np
from tqdm import tqdm
from dqn_utils import *
import torch.nn.functional as F
from collections import namedtuple
from torch.autograd import Variable
from tensorboardX import SummaryWriter
import torchvision.transforms as transforms
# 
# Configuration.
def getTensorConfiguration():
    use_cuda = torch.cuda.is_available()
    FloatTensor = torch.cuda.FloatTensor if use_cuda else torch.FloatTensor
    LongTensor = torch.cuda.LongTensor if use_cuda else torch.LongTensor
    ByteTensor = torch.cuda.ByteTensor if use_cuda else torch.ByteTensor
    # 
    # Default transforms.
    def cpuTensorImg(x):
        return torch.from_numpy(x.transpose((0,3,1,2))).type(FloatTensor).div_(255)
    def cpuTensor(x):
        return torch.from_numpy(x)
    toTensorImg = cpuTensorImg
    toTensor = cpuTensor
    # 
    # Cuda transforms.
    if use_cuda:
        def cudaTensorImg(x):
            ret = torch.from_numpy(x.transpose((0,3,1,2))).contiguous().cuda(async=True).type(FloatTensor).div_(255)
            return ret
        def cudaTensor(x):
            ret = torch.from_numpy(x).cuda(async=True)
            return ret
        toTensorImg = cudaTensorImg
        toTensor = cudaTensor
    return toTensorImg, toTensor, use_cuda
# 
# Visualize a batch.
def visobs(obs):
    from PIL import Image
    obsBatch = obs.data.cpu().numpy()
    for i, obs in enumerate(obsBatch):
        for plane in obs:
            img = Image.fromarray(plane*255)
            img.show()
        if i == 5:
            sys.exit(0)
# 
# Logging configuration.
def logEpochTensorboard(logger, model, epochSummary, t):
    # logger.add_scalar('%s_loss'%epochSummary['phase'], epochSummary['loss'], epochSummary['epoch'])
    # logger.add_scalar('%s_acc'%epochSummary['phase'], epochSummary['acc'], epochSummary['epoch'])
    # labels = epochSummary['data']['label']
    # for i in range(epochSummary['data']['label'].shape[0]):
    #     logger.add_image('{}_image_i-{}_epoch-{}_pre-:{}_label-{}'.format(epochSummary['phase'], i, epochSummary['epoch'], epochSummary['pred'][i], int(labels[i])), epochSummary['data']['img'][i]*math.sqrt(0.06342617) + 0.59008044, epochSummary['epoch'])
    for key in epochSummary:
        logger.add_scalar(key, epochSummary[key], t)
    for name, param in model.named_parameters():
        logger.add_histogram(name, param.clone().cpu().data.numpy(), t)
#
# Write everything as needed.
def closeTensorboard(logger):
    logger.close()
#
# When not using tensor board.
def doNothing(logger = None, model = None, tmp = None, tmp1 = None):
    pass
# 
# Training fn.
def learn(env,
          q_func,
          optimizer,
          lr_schedule,
          lr_scheduler,
          exploration=LinearSchedule(1000000, 0.1),
          stopping_criterion=None,
          replay_buffer_size=1000000,
          batch_size=32,
          gamma=0.99,
          learning_starts=50000,
          learning_freq=4,
          frame_history_len=4,
          target_update_freq=10000,
          grad_norm_clipping=10,
          useTB=False):
    """Run Deep Q-learning algorithm.

    You can specify your own convnet using q_func.

    All schedules are w.r.t. total number of steps taken in the environment.

    Parameters
    ----------
    env: gym.Env
        gym environment to train on.
    q_func: function
        Model to use for computing the q function. It should accept the
        following named arguments:
            img_in: tf.Tensor
                tensorflow tensor representing the input image
            num_actions: int
                number of actions
            scope: str
                scope in which all the model related variables
                should be created
            reuse: bool
                whether previously created variables should be reused.
    optimizer_spec: OptimizerSpec
        Specifying the constructor and kwargs, as well as learning rate schedule
        for the optimizer
    exploration: rl_algs.deepq.utils.schedules.Schedule
        schedule for probability of chosing random action.
    stopping_criterion: (env, t) -> bool
        should return true when it's ok for the RL algorithm to stop.
        takes in env and the number of steps executed so far.
    replay_buffer_size: int
        How many memories to store in the replay buffer.
    batch_size: int
        How many transitions to sample each time experience is replayed.
    gamma: float
        Discount Factor
    learning_starts: int
        After how many environment steps to start replaying experiences
    learning_freq: int
        How many steps of environment to take between every experience replay
    frame_history_len: int
        How many past frames to include as input to the model.
    target_update_freq: int
        How many experience replay rounds (not steps!) to perform between
        each update to the target Q network
    grad_norm_clipping: float or None
        If not None gradients' norms are clipped to this value.
    """
    assert type(env.observation_space) == gym.spaces.Box
    assert type(env.action_space)      == gym.spaces.Discrete

    ###############
    # BUILD MODEL #
    ###############
    # 
    # Environment information.
    nAct = env.action_space.n
    # 
    # Information for tensor configuration.
    toTensorImg, toTensor, use_cuda = getTensorConfiguration()
    # 
    # Logging setup.
    logger = None
    logEpoch = doNothing
    closeLogger = doNothing
    if useTB:
        logger = SummaryWriter()
        logEpoch = logEpochTensorboard
        closeLogger = closeTensorboard

    # Here, you should fill in your own code to compute the Bellman error. This requires
    # evaluating the current and next Q-values and constructing the corresponding error.
    # TensorFlow will differentiate this error for you, you just need to pass it to the
    # optimizer. See assignment text for details.
    # Your code should produce one scalar-valued tensor: total_error
    # This will be passed to the optimizer in the provided code below.
    # Your code should also produce two collections of variables:
    # q_func_vars
    # target_q_func_vars
    # These should hold all of the variables of the Q-function network and target network,
    # respectively. A convenient way to get these is to make use of TF's "scope" feature.
    # For example, you can create your Q-function network with the scope "q_func" like this:
    # <something> = q_func(obs_t_float, num_actions, scope="q_func", reuse=False)
    # And then you can obtain the variables like this:
    # q_func_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope='q_func')
    # Older versions of TensorFlow may require using "VARIABLES" instead of "GLOBAL_VARIABLES"
    ######

    def bellmanError(trainNet, targetNet, samples, gamma):
        obs_batch, act_batch, rew_batch, next_obs_batch, done_mask = samples
        #
        # Convert everything to be tensors, send to the GPU as needed.
        notDoneMask = (done_mask == False).astype(np.uint8)
        nextValidObs = next_obs_batch.compress(notDoneMask, axis=0)
        act = Variable(toTensor(act_batch))
        rew = Variable(toTensor(rew_batch))
        obs = Variable(toTensorImg(obs_batch))
        expectedQ = Variable(toTensor(np.zeros((batch_size), dtype=np.float32)))
        nextValidObs = Variable(toTensorImg(nextValidObs), volatile = True)
        notDoneTensor = Variable(toTensor(notDoneMask))
        #
        # Forward through both networks.
        trainQ = torch.gather(trainNet(obs), 1, act.unsqueeze_(1))
        #
        # Not all have a next observation -> some finished.
        targetQValid, _ = targetNet(nextValidObs).max(1)
        expectedQ[notDoneTensor] = targetQValid
        #
        # Calculate the belman error.
        expectedQ.volatile = False
        expectedQ = expectedQ.mul_(gamma) + rew
        return trainQ, expectedQ
    ######

    # construct the replay buffer
    replay_buffer = ReplayBuffer(replay_buffer_size, frame_history_len)

    ###############
    # RUN ENV     #
    ###############
    num_param_updates = 0
    mean_episode_reward      = -float('nan')
    best_mean_episode_reward = -float('inf')
    last_obs = env.reset()
    LOG_EVERY_N_STEPS = 10000
    PROGRESS_UPDATE_FREQ = 100
    trainQ_func = q_func
    targetQ_func = copy.deepcopy(trainQ_func).eval()
    runningLoss = 0
    #
    # Send networks to CUDA.
    if use_cuda:
        trainQ_func.cuda()
        targetQ_func.cuda()
    #
    # Training loop.
    pbar = None
    for t in itertools.count():
        ### 1. Check stopping criterion
        if stopping_criterion is not None and stopping_criterion(env, t):
            break
        ### 2. Step the env and store the transition
        # At this point, "last_obs" contains the latest observation that was
        # recorded from the simulator. Here, your code needs to store this
        # observation and its outcome (reward, next observation, etc.) into
        # the replay buffer while stepping the simulator forward one step.
        # At the end of this block of code, the simulator should have been
        # advanced one step, and the replay buffer should contain one more
        # transition.
        # Specifically, last_obs must point to the new latest observation.
        # Useful functions you'll need to call:
        # obs, reward, done, info = env.step(action)
        # this steps the environment forward one step
        # obs = env.reset()
        # this resets the environment if you reached an episode boundary.
        # Don't forget to call env.reset() to get a new observation if done
        # is true!!
        # Note that you cannot use "last_obs" directly as input
        # into your network, since it needs to be processed to include context
        # from previous frames. You should check out the replay buffer
        # implementation in dqn_utils.py to see what functionality the replay
        # buffer exposes. The replay buffer has a function called
        # encode_recent_observation that will take the latest observation
        # that you pushed into the buffer and compute the corresponding
        # input that should be given to a Q network by appending some
        # previous frames.
        # Don't forget to include epsilon greedy exploration!
        # And remember that the first time you enter this loop, the model
        # may not yet have been initialized (but of course, the first step
        # might as well be random, since you haven't trained your net...)

        #####
        #
        # Store the latest frame in the replay buffer.
        storeIndex = replay_buffer.store_frame(last_obs)
        #
        # Epsilon greedy exploration.
        action = None
        if random.random() < exploration.value(t) or t < learning_starts:
            action = np.random.randint(0, nAct, dtype=np.int_)
        else:
            obs = toTensorImg(np.expand_dims(replay_buffer.encode_recent_observation(), axis=0))
            #
            # Forward through network.
            _, action = trainQ_func(Variable(obs, volatile=True)).max(1)
            # _, action = targetQ_func(Variable(obs, volatile=True)).max(1)
            action = action.data.cpu().numpy().astype(np.int_)

        last_obs, reward, done, info = env.step(action)
        replay_buffer.store_effect(storeIndex, action, reward, done)
        #
        # Reset as needed.
        if done:
            last_obs = env.reset()

        #####

        # at this point, the environment should have been advanced one step (and
        # reset if done was true), and last_obs should point to the new latest
        # observation

        ### 3. Perform experience replay and train the network.
        # note that this is only done if the replay buffer contains enough samples
        # for us to learn something useful -- until then, the model will not be
        # initialized and random actions should be taken
        if (t > learning_starts and
                t % learning_freq == 0 and
                replay_buffer.can_sample(batch_size)):
            # Here, you should perform training. Training consists of four steps:
            # 3.a: use the replay buffer to sample a batch of transitions (see the
            # replay buffer code for function definition, each batch that you sample
            # should consist of current observations, current actions, rewards,
            # next observations, and done indicator).
            # 3.b: initialize the model if it has not been initialized yet; to do
            # that, call
            #    initialize_interdependent_variables(session, tf.global_variables(), {
            #        obs_t_ph: obs_t_batch,
            #        obs_tp1_ph: obs_tp1_batch,
            #    })
            # where obs_t_batch and obs_tp1_batch are the batches of observations at
            # the current and next time step. The boolean variable model_initialized
            # indicates whether or not the model has been initialized.
            # Remember that you have to update the target network too (see 3.d)!
            # 3.c: train the model. To do this, you'll need to use the train_fn and
            # total_error ops that were created earlier: total_error is what you
            # created to compute the total Bellman error in a batch, and train_fn
            # will actually perform a gradient step and update the network parameters
            # to reduce total_error. When calling session.run on these you'll need to
            # populate the following placeholders:
            # obs_t_ph
            # act_t_ph
            # rew_t_ph
            # obs_tp1_ph
            # done_mask_ph
            # (this is needed for computing total_error)
            # learning_rate -- you can get this from optimizer_spec.lr_schedule.value(t)
            # (this is needed by the optimizer to choose the learning rate)
            # 3.d: periodically update the target network by calling
            # session.run(update_target_fn)
            # you should update every target_update_freq steps, and you may find the
            # variable num_param_updates useful for this (it was initialized to 0)

            #
            # Sample from replay buffer.
            sample = replay_buffer.sample(batch_size)
            #
            # Train the model
            trainQ, targetQ = bellmanError(trainQ_func, targetQ_func, sample, gamma)
            #
            # Calculate Huber loss.
            loss = F.smooth_l1_loss(trainQ, targetQ)
            runningLoss += loss.data[0]
            # 
            # Optimize the model.
            optimizer.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm(trainQ_func.parameters(), grad_norm_clipping)
            optimizer.step()
            lr_schedule.step(t)
            num_param_updates += 1
            #
            # Update the target network as needed (target_update_freq).
            if num_param_updates % target_update_freq == 0:
                targetQ_func = copy.deepcopy(trainQ_func)
                targetQ_func.eval()
                if use_cuda:
                    targetQ_func.cuda()

        ### 4. Log progress
        episode_rewards = get_wrapper_by_name(env, "Monitor").get_episode_rewards()
        if len(episode_rewards) > 0:
            mean_episode_reward = np.mean(episode_rewards[-100:])
        if len(episode_rewards) > 100:
            best_mean_episode_reward = max(best_mean_episode_reward, mean_episode_reward)
        if t % LOG_EVERY_N_STEPS == 0:
            print("Timestep %d" % (t,))
            print("mean reward (100 episodes) %f" % mean_episode_reward)
            print("best mean reward %f" % best_mean_episode_reward)
            print("episodes %d" % len(episode_rewards))
            print("exploration %f" % exploration.value(t))
            print("learning_rate_schedule %f" % lr_scheduler.value(t))
            print("learning_rate ", lr_schedule.get_lr())
            sys.stdout.flush()
            if pbar is not None:
                pbar.close()
            pbar = tqdm(total=LOG_EVERY_N_STEPS)
            summary = {
                'Mean reward (100 episodes)': mean_episode_reward,
                'Best mean reward': best_mean_episode_reward,
                'Episodes': len(episode_rewards),
                'Learning rate': lr_schedule.get_lr()[0],
                'Train loss': runningLoss / LOG_EVERY_N_STEPS,
            }
            logEpoch(logger, trainQ_func, summary, t)
            runningLoss = 0
        if t % PROGRESS_UPDATE_FREQ == 0:
            pbar.update(100)
    closeLogger()