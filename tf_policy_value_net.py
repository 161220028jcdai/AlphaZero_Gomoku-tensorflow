# -*- coding: utf-8 -*-
"""
Created on Fri Feb  9 12:29:58 2018

@author: zou
"""
import tensorflow as tf
import os


class PolicyValueNet():
    """policy-value network """
    def __init__(self, board_width, board_height, net_params=None):
        tf.reset_default_graph()
        self.board_width = board_width
        self.board_height = board_height
        self.model_file = './model/tf_policy_8_8_5_model'
        self.sess = tf.Session()
        self.l2_const = 1e-4  #  coef of l2 penalty 
        self.create_policy_value_net() 
        self._loss_train_op()
        self.saver = tf.train.Saver()
        self.restore_model()

        if net_params:
            saver = tf.train.Saver()
            saver.restore(self.sess, net_params)  
            
    def create_policy_value_net(self):
        """create the policy value network """    
        with tf.name_scope("inputs"):
            self.state_input = tf.placeholder(tf.float32, shape=[None, 4, self.board_width, self.board_height], name="state")
            self.winner = tf.placeholder(tf.float32, shape=[None], name="winner") 
            self.winner_reshape = tf.reshape(self.winner, [-1,1])
            self.mcts_probs = tf.placeholder(tf.float32, shape=[None, self.board_width*self.board_height], name="mcts_probs")
        
        # conv layers
        conv1 = tf.layers.conv2d(self.state_input, filters=32, kernel_size=3,
                         strides=1, padding="SAME", data_format='channels_first',
                         activation=tf.nn.relu, name="conv1")
        conv2 = tf.layers.conv2d(conv1, filters=64, kernel_size=3,
                         strides=1, padding="SAME", data_format='channels_first',
                         activation=tf.nn.relu, name="conv2")               
        conv3 = tf.layers.conv2d(conv2, filters=128, kernel_size=3,
                         strides=1, padding="SAME", data_format='channels_first',
                         activation=tf.nn.relu, name="conv3")
        
        # action policy layers
        policy_net = tf.layers.conv2d(conv3, filters=4, kernel_size=1,
                         strides=1, padding="SAME", data_format='channels_first',
                         activation=tf.nn.relu, name="policy_net")
        policy_net_flat = tf.reshape(policy_net, shape=[-1, 4*self.board_width*self.board_height])
        policy_net_out = tf.layers.dense(policy_net_flat, self.board_width*self.board_height, name="output")
        self.action_probs = tf.nn.softmax(policy_net_out, name="policy_net_proba")

        # state value layers
        value_net = tf.layers.conv2d(conv3, filters=2, kernel_size=1, 
                                     data_format='channels_first', name='value_conv', activation=tf.nn.relu)
        value_net = tf.layers.dense(tf.contrib.layers.flatten(value_net), 64, activation=tf.nn.relu)
        self.value = tf.layers.dense(value_net, units=1, activation=tf.nn.tanh)
    
    def get_policy_value(self, state_batch):
         # get action probs and state score value
        action_probs, value = self.sess.run([self.action_probs, self.value],
                                    feed_dict={self.state_input: state_batch})       
        return action_probs, value

    def policy_value_fn(self, board):
        """
        input: board
        output: a list of (action, probability) tuples for each available action and the score of the board state
        """
        legal_positions = board.availables
        current_state = board.current_state()
        act_probs, value = self.sess.run([self.action_probs, self.value], 
                                    feed_dict={self.state_input: current_state.reshape(-1, 4, self.board_width, self.board_height)})
        act_probs = zip(legal_positions, act_probs.flatten()[legal_positions])
        return act_probs, value[0][0]
    
    def _loss_train_op(self):
        """
        Three loss terms：
        loss = (z - v)^2 + pi^T * log(p) + c||theta||^2
        """
        l2_penalty = 0
        for v in tf.trainable_variables():
            if not 'bias' in v.name.lower():
                l2_penalty += tf.nn.l2_loss(v)
        value_loss = tf.reduce_mean(tf.square(self.winner_reshape - self.value))
        cross_entropy = tf.nn.softmax_cross_entropy_with_logits(logits=self.action_probs, labels=self.mcts_probs)
        policy_loss = tf.reduce_mean(cross_entropy)
        self.loss =  value_loss + policy_loss + self.l2_const*l2_penalty
        # policy entropy，for monitoring only
        self.entropy = policy_loss
        # get the train op   
        optimizer = tf.train.AdamOptimizer()
        self.training_op = optimizer.minimize(self.loss)
    
    def train_step(self, state_batch, mcts_probs_batch, winner_batch, show_loss=0):
        feed_dict = {self.state_input : state_batch,
                     self.mcts_probs : mcts_probs_batch, 
                     self.winner : winner_batch,}
        if show_loss:
            loss, entropy, _ = self.sess.run([self.loss, self.entropy, self.training_op],
                                         feed_dict=feed_dict)
            return loss, entropy
        else:
            self.sess.run(self.training_op,
                          feed_dict=feed_dict)
    
    def restore_model(self):        
        if os.path.exists(self.model_file + '.meta'):
            self.saver.restore(self.sess, self.model_file)
        else:
            self.sess.run(tf.global_variables_initializer())
            
    def get_model_params(self):
        gvars = tf.get_collection(tf.GraphKeys.TRAINABLE_VARIABLES)
        return {gvar.op.name: value for gvar, value in zip(gvars, self.sess.run(gvars))}
    
