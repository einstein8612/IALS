import torch
import argparse
import numpy as np
import csv
import sys
sys.path.append("..") 
from influence.network import InfluenceModel
from influence.data_collector import DataCollector
from agents.random_agent import RandomAgent
from simulators.warehouse.warehouse import Warehouse
import torch.nn as nn
import random
import matplotlib.pyplot as plt
import os
import yaml

class InfluenceNetwork(object):
    """
    """
    def __init__(self, agent, parameters, data_file, run_id):
        """
        """
        # parameters = read_parameters('../influence/configs/influence.yaml')
        self._seq_len = parameters['seq_len']
        self._episode_length = parameters['episode_length']
        self._lr = parameters['lr']
        self._n_epochs = parameters['n_epochs']
        self._hidden_layer_size = parameters['hidden_layer_size']
        self._batch_size = parameters['batch_size']
        self.n_sources = parameters['n_sources']
        self.input_size = parameters['input_size']
        self.output_size = parameters['output_size']
        self.curriculum = parameters['curriculum']
        self.aug_obs = parameters['aug_obs']
        self.parameters = parameters
        self._data_file = data_file
        self.model = InfluenceModel(self.input_size, self._hidden_layer_size, self.n_sources, self.output_size)
        weights1 = torch.FloatTensor([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])
        weights2 = torch.FloatTensor([1.0, 1.0])
        self.loss_function = [nn.CrossEntropyLoss(weight=weights1),  nn.CrossEntropyLoss(weight=weights2)]
        self.optimizer = torch.optim.Adam(self.model.parameters(), lr=self._lr, weight_decay=0.001)
        self.checkpoint_path = parameters['checkpoint_path'] + str(run_id)
        if parameters['load_model']:
            self._load_model()
        if self.curriculum:
            self.strength = 0.5
            self.strength_increment = 0.025
        else:
            self.strength = 1

    def train(self, step):
        data = self._read_data(self._data_file)
        inputs, targets = self._form_sequences(np.array(data))
        train_inputs, train_targets, test_inputs, test_targets = self._split_train_test(inputs, targets)
        self._train(train_inputs, train_targets, test_inputs, test_targets)
        self._test(test_inputs, test_targets)
        self._save_model()
        if self.curriculum:
            self.strength += self.strength_increment
    
    def predict(self, obs):
        obs_tensor = torch.reshape(torch.FloatTensor(obs), (1,1,-1))
        _, probs = self.model(obs_tensor)
        probs = [prob[0] for prob in probs]
        return probs
    
    def reset(self):
        self.model.reset()


### Private methods ###        

    def _read_data(self, data_file):
        data = []
        with open(data_file) as data_file:
            csv_reader = csv.reader(data_file, delimiter=',')
            for row in csv_reader:
                data.append([int(element) for element in row])
        return data

    def _form_sequences(self, data):
        n_episodes = len(data)//self._episode_length
        inputs = []
        targets = []
        for episode in range(n_episodes):
            for seq in range(self._episode_length - (self._seq_len - 1)):
                start = episode*self._episode_length+seq
                end = episode*self._episode_length+seq+self._seq_len
                inputs.append(data[start:end, 25:41])
                targets.append(data[start:end, 41:])
        return inputs, targets

    def _split_train_test(self, inputs, targets):
        test_size = int(0.1*len(inputs))
        train_inputs, train_targets = inputs[:-test_size], targets[:-test_size] 
        test_inputs, test_targets = inputs[-test_size:], targets[-test_size:]
        return train_inputs, train_targets, test_inputs, test_targets

    def _train(self, train_inputs, train_targets, test_inputs, test_targets):
        seqs = torch.FloatTensor(train_inputs)
        targets = torch.FloatTensor(train_targets)
        for e in range(self._n_epochs):
            permutation = torch.randperm(len(seqs))
            if e % 10 == 0:
                test_loss = self._test(test_inputs, test_targets)
                print(f'epoch: {e:3} test loss: {test_loss.item():10.8f}')
            for i in range(0, len(seqs) - len(seqs) % self._batch_size, self._batch_size):
                indices = permutation[i:i+self._batch_size]
                seqs_batch = seqs[indices]
                targets_batch = targets[indices]
                self.model.hidden_cell = (torch.randn(1, self._batch_size, self._hidden_layer_size),
                                          torch.randn(1, self._batch_size, self._hidden_layer_size))
                logits, probs = self.model(seqs_batch)
                end = 0
                self.optimizer.zero_grad()
                loss = 0
                for s in range(self.n_sources):
                    start = end 
                    end += self.output_size[s]
                    # breakpoint()
                    # single_loss = self.loss_function[s % 2](logits[s][:,-1,:], torch.argmax(targets_batch[:, start:end], dim=1))
                    single_loss = self.loss_function[s % 2](logits[s].view(-1, self.output_size[s]), torch.argmax(targets_batch[:, :, start:end], dim=2).view(-1))
                    loss += single_loss
                loss.backward()
                self.optimizer.step()
        test_loss = self._test(test_inputs, test_targets)
        print(f'epoch: {e+1:3} test loss: {test_loss.item():10.8f}')
        self.model.reset()

    def _test(self, inputs, targets):
        inputs = torch.FloatTensor(inputs)
        targets = torch.FloatTensor(targets)
        loss = 0
        self.model.hidden_cell = (torch.randn(1, len(inputs), self._hidden_layer_size),
                                  torch.randn(1, len(inputs), self._hidden_layer_size))
        logits, probs = self.model(inputs)
        self.img1 = None
        end = 0
        targets_counts = []
        for s in range(self.n_sources):
            start = end
            end += self.output_size[s]
            # loss += self.loss_function[s % 2](logits[s][:,-1,:], torch.argmax(targets[:, start:end], dim=1))
            # breakpoint()
            loss += self.loss_function[s % 2](logits[s].view(-1, self.output_size[s]), torch.argmax(targets[:, :, start:end], dim=2).view(-1))
            # from collections import Counter
            # targets_counts = Counter(torch.argmax(targets[:, start:end], dim=1).detach().numpy())
            # print(targets_counts)
            # probs_counts = np.sum(probs[s], axis=0)
            # print(probs_counts)
            # for i in range(len(inputs)):
                # self._plot_prediction(probs[s][i], targets[i, start:end])
        return loss

    def _plot_prediction(self, prediction, target):
        prediction = prediction.detach().numpy()
        prediction = np.reshape(np.append(prediction, [prediction[5]]*19), (5,5))
        target = target.detach().numpy()
        target = np.reshape(np.append(target, [target[5]]*19), (5,5))
        if self.img1 is None:
            fig = plt.figure(figsize=(10,6))
            sub1 = fig.add_subplot(1, 2, 2)
            self.img1 = sub1.imshow(prediction, vmin=0, vmax=1)
            sub2 = fig.add_subplot(1, 2, 1)
            self.img2 = sub2.imshow(target, vmin=0, vmax=1)
            plt.tight_layout()
        else:
            self.img1.set_data(prediction)
            self.img2.set_data(target)
        plt.pause(0.5)
        plt.draw()

    def _save_model(self):
        if not os.path.exists(self.checkpoint_path):
            os.makedirs(self.checkpoint_path)
        torch.save({'model_state_dict': self.model.state_dict(),
                    'optimizer_state_dict': self.optimizer.state_dict()}, 
                    os.path.join(self.checkpoint_path, 'checkpoint'))
    
    def _load_model(self):
        checkpoint = torch.load(os.path.join(self.checkpoint_path, 'checkpoint'))
        self.model.load_state_dict(checkpoint['model_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])

def read_parameters(config_file):
    with open(config_file) as file:
        parameters = yaml.load(file, Loader=yaml.FullLoader)
    return parameters['parameters']


if __name__ == '__main__':
    simulator = Warehouse()
    agent = RandomAgent(simulator.action_space.n, None)
    parameters = read_parameters('../influence/configs/influence.yaml')
    trainer = InfluenceNetwork(agent, simulator, parameters, 0)
    trainer.train()
