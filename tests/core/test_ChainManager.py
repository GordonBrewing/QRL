# coding=utf-8
# Distributed under the MIT software license, see the accompanying
# file LICENSE or http://www.opensource.org/licenses/mit-license.php.
from unittest import TestCase

from mock import mock, MagicMock, Mock
from pyqryptonight.pyqryptonight import StringToUInt256

from qrl.core import config
from qrl.core.Block import Block
from qrl.core.PoWValidator import PoWValidator
from qrl.core.ChainManager import ChainManager
from qrl.core.DifficultyTracker import DifficultyTracker
from qrl.core.GenesisBlock import GenesisBlock
from qrl.core.State import State
from qrl.core.Transaction import SlaveTransaction, TransferTransaction
from tests.misc.helper import get_alice_xmss, get_bob_xmss, set_data_dir, get_random_xmss


class TestChainManager(TestCase):
    def __init__(self, *args, **kwargs):
        super(TestChainManager, self).__init__(*args, **kwargs)

    def test_load(self):
        with set_data_dir('no_data'):
            with State() as state:
                genesis_block = GenesisBlock()
                chain_manager = ChainManager(state)
                chain_manager.load(genesis_block)
                block = state.get_block(GenesisBlock().headerhash)
                self.assertIsNotNone(block)

    def test_simple_add_block(self):
        with set_data_dir('no_data'):
            with State() as state:
                state.get_measurement = MagicMock(return_value=10000000)
                alice_xmss = get_alice_xmss()

                genesis_block = GenesisBlock()
                chain_manager = ChainManager(state)
                chain_manager.load(genesis_block)

                chain_manager._difficulty_tracker = Mock()
                dt = DifficultyTracker()
                tmp_difficulty = StringToUInt256('2')
                tmp_boundary = dt.get_target(tmp_difficulty)
                chain_manager._difficulty_tracker.get = MagicMock(return_value=(tmp_difficulty, tmp_boundary))

                block = state.get_block(genesis_block.headerhash)
                self.assertIsNotNone(block)

                with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                    time_mock.return_value = 1615270948  # Very high to get an easy difficulty

                    block_1 = Block.create(block_number=1,
                                           prevblock_headerhash=genesis_block.headerhash,
                                           transactions=[],
                                           signing_xmss=alice_xmss,
                                           master_address=alice_xmss.address,
                                           nonce=1)

                    while not PoWValidator().validate_mining_nonce(state, block_1.blockheader, False):
                        block_1.set_mining_nonce(block_1.mining_nonce + 1)

                    result = chain_manager.add_block(block_1)

                self.assertTrue(result)
                self.assertEqual(chain_manager.last_block, block_1)

    def test_multi_output_transaction_add_block(self):
        with set_data_dir('no_data'):
            with State() as state:
                state.get_measurement = MagicMock(return_value=10000000)
                alice_xmss = get_alice_xmss()
                bob_xmss = get_bob_xmss()
                random_xmss = get_random_xmss()
                transfer_transaction = TransferTransaction.create(addr_from=bob_xmss.address,
                                                                  addrs_to=[alice_xmss.address, random_xmss.address],
                                                                  amounts=[40 * int(config.dev.shor_per_quanta),
                                                                           59 * int(config.dev.shor_per_quanta)],
                                                                  fee=1 * config.dev.shor_per_quanta,
                                                                  xmss_pk=bob_xmss.pk)
                transfer_transaction._data.nonce = 1
                transfer_transaction.sign(bob_xmss)

                genesis_block = GenesisBlock()
                chain_manager = ChainManager(state)
                chain_manager.load(genesis_block)

                chain_manager._difficulty_tracker = Mock()
                dt = DifficultyTracker()
                tmp_difficulty = StringToUInt256('2')
                tmp_boundary = dt.get_target(tmp_difficulty)
                chain_manager._difficulty_tracker.get = MagicMock(return_value=(tmp_difficulty, tmp_boundary))

                block = state.get_block(genesis_block.headerhash)
                self.assertIsNotNone(block)

                with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                    time_mock.return_value = 1615270948  # Very high to get an easy difficulty

                    block_1 = Block.create(block_number=1,
                                           prevblock_headerhash=genesis_block.headerhash,
                                           transactions=[transfer_transaction],
                                           signing_xmss=alice_xmss,
                                           master_address=alice_xmss.address,
                                           nonce=1)

                    while not PoWValidator().validate_mining_nonce(state, block_1.blockheader, False):
                        block_1.set_mining_nonce(block_1.mining_nonce + 1)

                    result = chain_manager.add_block(block_1)

                self.assertTrue(result)
                self.assertEqual(chain_manager.last_block, block_1)

                bob_addr_state = state.get_address(bob_xmss.address)
                alice_addr_state = state.get_address(alice_xmss.address)
                random_addr_state = state.get_address(random_xmss.address)

                self.assertEqual(bob_addr_state.balance, 0)
                self.assertEqual(alice_addr_state.balance,
                                 140 * int(config.dev.shor_per_quanta) + block_1.block_reward + block_1.fee_reward)
                self.assertEqual(random_addr_state.balance, 159 * int(config.dev.shor_per_quanta))

    @mock.patch("qrl.core.DifficultyTracker.DifficultyTracker.get")
    def test_add_block(self, mock_difficulty_tracker_get):
        """
        Testing add_block, with fork logic
        :return:
        """
        with set_data_dir('no_data'):
            with State() as state:
                state.get_measurement = MagicMock(return_value=10000000)

                alice_xmss = get_alice_xmss()
                bob_xmss = get_bob_xmss()

                genesis_block = GenesisBlock()
                chain_manager = ChainManager(state)
                mock_difficulty_tracker_get.return_value = [config.dev.mining_setpoint_blocktime, 2]
                chain_manager.load(genesis_block)

                chain_manager._difficulty_tracker = Mock()
                tmp_difficulty = StringToUInt256('2')
                tmp_boundary = DifficultyTracker.get_target(tmp_difficulty)
                mock_difficulty_tracker_get.return_value = [tmp_difficulty, tmp_boundary]

                block = state.get_block(genesis_block.headerhash)
                self.assertIsNotNone(block)

                slave_tx = SlaveTransaction.create(addr_from=alice_xmss.address,
                                                   slave_pks=[bob_xmss.pk],
                                                   access_types=[0],
                                                   fee=0,
                                                   xmss_pk=alice_xmss.pk)
                slave_tx.sign(alice_xmss)
                slave_tx._data.nonce = 2
                self.assertTrue(slave_tx.validate())
                with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                    time_mock.return_value = 1615270948  # Very high to get an easy difficulty

                    block_1 = Block.create(block_number=1,
                                           prevblock_headerhash=genesis_block.headerhash,
                                           transactions=[slave_tx],
                                           signing_xmss=alice_xmss,
                                           master_address=alice_xmss.address,
                                           nonce=1)

                    while not PoWValidator().validate_mining_nonce(state, block_1.blockheader, False):
                        block_1.set_mining_nonce(block_1.mining_nonce + 1)

                    result = chain_manager.add_block(block_1)

                self.assertTrue(result)
                self.assertEqual(chain_manager.last_block, block_1)

                alice_state = chain_manager.get_address(alice_xmss.address)

                self.assertEqual(len(alice_state.slave_pks_access_type), 1)
                self.assertTrue(str(bob_xmss.pk) in alice_state.slave_pks_access_type)

                with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                    time_mock.return_value = 1715270948  # Very high to get an easy difficulty
                    block = Block.create(block_number=1,
                                         prevblock_headerhash=genesis_block.headerhash,
                                         transactions=[],
                                         signing_xmss=bob_xmss,
                                         master_address=bob_xmss.address,
                                         nonce=1)

                    while not PoWValidator().validate_mining_nonce(state, block.blockheader, False):
                        block.set_mining_nonce(block.mining_nonce + 1)

                    result = chain_manager.add_block(block)

                self.assertTrue(result)
                self.assertEqual(chain_manager.last_block, block_1)

                block = state.get_block(block.headerhash)
                self.assertIsNotNone(block)

                with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                    time_mock.return_value = 1815270948  # Very high to get an easy difficulty
                    block_2 = Block.create(block_number=2,
                                           prevblock_headerhash=block.headerhash,
                                           transactions=[],
                                           signing_xmss=bob_xmss,
                                           master_address=bob_xmss.address,
                                           nonce=2)

                    while not PoWValidator().validate_mining_nonce(state, block_2.blockheader, False):
                        block_2.set_mining_nonce(block_2.mining_nonce + 1)

                    result = chain_manager.add_block(block_2)

                self.assertTrue(result)
                self.assertEqual(chain_manager.last_block.block_number, block_2.block_number)
                self.assertEqual(chain_manager.last_block.to_json(), block_2.to_json())

    def test_orphan_block(self):
        """
        Testing add_block logic in case of orphan_blocks
        :return:
        """
        with mock.patch('qrl.core.config.DevConfig') as devconfig:
            devconfig.genesis_difficulty = 2
            devconfig.minimum_minting_delay = 10
            with set_data_dir('no_data'):
                with State() as state:  # FIXME: Move state to temporary directory
                    state.get_measurement = MagicMock(return_value=10000000)
                    genesis_block = GenesisBlock()

                    chain_manager = ChainManager(state)
                    chain_manager.load(genesis_block)

                    chain_manager._difficulty_tracker = Mock()
                    dt = DifficultyTracker()
                    tmp_difficulty = StringToUInt256('2')
                    tmp_boundary = dt.get_target(tmp_difficulty)
                    chain_manager._difficulty_tracker.get = MagicMock(return_value=(tmp_difficulty, tmp_boundary))

                    block = state.get_block(genesis_block.headerhash)
                    self.assertIsNotNone(block)
                    alice_xmss = get_alice_xmss()

                    with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                        time_mock.return_value = 1519601174  # Very high to get an easy difficulty
                        block_1 = Block.create(block_number=1,
                                               prevblock_headerhash=genesis_block.headerhash,
                                               transactions=[],
                                               signing_xmss=alice_xmss,
                                               master_address=alice_xmss.address,
                                               nonce=1)
                        block_1.set_mining_nonce(10)

                        while not PoWValidator().validate_mining_nonce(state, block_1.blockheader, False):
                            block_1.set_mining_nonce(block_1.mining_nonce + 1)

                        result = chain_manager.add_block(block_1)

                    self.assertTrue(result)
                    self.assertEqual(chain_manager.last_block, block_1)

                    bob_xmss = get_bob_xmss()

                    with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                        time_mock.return_value = 1519601174 + devconfig.minimum_minting_delay * 2
                        block = Block.create(block_number=1,
                                             prevblock_headerhash=genesis_block.headerhash,
                                             transactions=[],
                                             signing_xmss=bob_xmss,
                                             master_address=bob_xmss.address,
                                             nonce=1)
                        block.set_mining_nonce(18)

                        while not PoWValidator().validate_mining_nonce(state, block.blockheader, False):
                            block.set_mining_nonce(block.mining_nonce + 1)

                    with mock.patch('qrl.core.misc.ntp.getTime') as time_mock:
                        time_mock.return_value = 1519601174 + devconfig.minimum_minting_delay * 3
                        block_2 = Block.create(block_number=2,
                                               prevblock_headerhash=block.headerhash,
                                               transactions=[],
                                               signing_xmss=bob_xmss,
                                               master_address=bob_xmss.address,
                                               nonce=2)
                        block_2.set_mining_nonce(10)

                    result = chain_manager.add_block(block_2)
                    self.assertTrue(result)

                    result = chain_manager.add_block(block)
                    self.assertTrue(result)

                    block = state.get_block(block.headerhash)
                    self.assertIsNotNone(block)

                    self.assertEqual(chain_manager.last_block.block_number, block_2.block_number)
                    self.assertEqual(chain_manager.last_block.headerhash, block_2.headerhash)
