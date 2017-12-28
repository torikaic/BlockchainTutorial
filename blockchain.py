"""
ブロックチェーンの青写真 2017/12/25
チェーンを管理する。
トランザクションを保管し、チェーンへ新たなブロックを付加する支援をする。
"""

import hashlib
import json
from time import time
from urllib.parse import urlparse
from uuid import uuid4

import requests
from flask import Flask, jsonify, request

class Blockchain:
    # コンストラクタ
    def __init__(self):
        # ブロックチェーンの保管を目的とする空リスト
        self.chain = []
        # トランザクションの保管を目的とする空リスト
        self.current_transactions = []

        # register_nodeでノード一覧を保持するためのset
        self.nodes = set()

        # Create the genesis block
        self.new_block(previous_hash='1', proof=100)

    # 新しいノードを登録する
    def register_node(self, address):
        """
        :param address: Adress of node. Eg.'http://192.168.0.5:5000'
        """

        parsed_url = urlparse(address)
        self.nodes.add(parsed_url.netloc)

    # チェーンが有効かを確認する
    # 各ブロックをループし、ハッシュ値とプルーフの両方を検出する
    def valid_chain(self, chain):
        """
        :param chain: A blockchain
        :return: True if valid, False if not
        """
        last_block = chain[0]
        current_index = 1

        while current_index < len(chain):
            block = chain[current_index]
            print(f'{last_block}')
            print(f'{block}')
            print("\n-------------\n")

            # Check that the hash of the block is correct
            if block['previous_hash'] != self.hash(last_block):
                return False

            # Check that the Proof of Work is correct
            if not self.valid_proof(last_block['proof'], block['proof']):
                return False

            last_block = block
            current_index += 1

        return True

    # 隣接する全てのノードをループし、チェーンを検証する
    # 自分のチェーンより長く有効なチェーンが見つかった場合
    # 自分のチェーンをそのチェーンに置き換える
    def resolve_conflicts(self):
        """
        :return: True if our chain was replaced, False is not
        """

        neighbours = self.nodes
        new_chain = None

        # We're only looking for chains longer than ours
        max_length = len(self.chain)

        # Grab and verify the chains from all the nodes in ouf network
        for node in neighbours:
            response = requests.get(f'http://{node}/chain')

            if response.status_code == 200:
                length = response.json()['length']
                chain = response.json()['chain']

                # Check if the length is longer and the chain is valid
                if length > max_length and self.valid_chain (chain):
                    max_length = length
                    new_chain = chain

        # Replace our chain if we discovered a new, valid chain longer than ours
        if new_chain:
            self.chain = new_chain
            return True

        return False


    def new_block(self, proof, previous_hash):
        """
        Creates a new Block and adds it to the chain

        :param proof: The proof given the Proof of Work algorithm
        :param previous_hash: Hash of previous Block
        :return: New Block
        """
        # ブロック
        block = {

            'index': len(self.chain) +1,
            'timestamp': time(),
            'transactions': self.current_transactions,
            'proof': proof,
            'previous_hash': previous_hash or self.hash(self.chain[-1])

        }

        # コンストラクタのトランザクションリストを初期化
        self.current_transactions = []

        # コンストラクタのチェーンにブロックを追加
        self.chain.append(block)

        return block

    # リストにトランザクションを追加する
    def new_transaction(self, sender, recipient, amount):
        """
        Creates a new transaction to go into the next mined Block

        :param sender: <str> Address of the Sender
        :param recipient: <str> Address of the Recipient
        :param amount: <int> Amount
        :return: <int> The index of the Block that will hold this transaction
        """

        self.current_transactions.append({
            'sender': sender,
            'recipient': recipient,
            'amount': amount,
        })

        # 次のマイニングで利用されることになるトランザクションのインデックス
        # （いまマイニングされたものの次のインデックス）を返す
        return self.last_block['index'] + 1

    @property
    def last_block(self):
        # Returns the last Block in the chain
        return self.chain[-1]

    @staticmethod
    def hash(block):
        """
        Creates a SHA-256 hash of a Block

        :param block: <dict> Block
        :return: <str>
        """

        # We must make sure that the Dictionary is Ordered,
        # or we'll have inconsistent hashes

        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()


    def proof_of_work(self, last_proof):
        """
        Simple Proof of work Algorithm:
        - Find a number p' such that hash(pp') contains
          leading 4 zeroes where p is previous p'
        - p is the previous proof, and p' is the new proof
        """

        proof = 0
        while self.valid_proof(last_proof, proof) is False:
            proof += 1

        return proof

    @staticmethod
    def valid_proof(last_proof, proof):
        """
        Validates the Proof

        :param last_proof: Previous Proof
        :param proof: Current Proof
        :return: True if correct, False if not.
        """

        guess = f'{last_proof}{proof}'.encode()
        guess_hash = hashlib.sha256(guess).hexdigest()
        # 0は4つで十分
        return guess_hash[:4] == "0000"

# ノードのインスタンス化
app = Flask(__name__)

# ノードの名前を無作為に作成
node_identifier = str(uuid4()).replace('_','')

# Blockchainクラスのインスタンス化
blockchain = Blockchain()

# GETリクエストである/mineエンドポイント
@app.route('/mine', methods=['GET'])
def mine():
    # We run the proof of work algorithm to get the next proof...
    last_block = blockchain.last_block
    last_proof = last_block['proof']
    proof = blockchain.proof_of_work(last_proof)

    # We must receive a reward for finding the proof.
    # The sender is "0" to signify that this node has mined a new coin.
    blockchain.new_transaction(
        sender="0",
        recipient=node_identifier,
        amount=1,
    )

    # Forge the new Block by adding it to the chain
    previous_hash = blockchain.hash(last_block)
    block = blockchain.new_block(proof, previous_hash)

    response = {
        'message':"New Block Forged",
        'index':block['index'],
        'transactions':block['transactions'],
        'proof':block['proof'],
        'previous_hash':block['previous_hash'],
    }
    return jsonify(response), 200

# POSTリクエストである/transactions/newエンドポイント
# このエンドポイントにデータを送信するので必要となる。
@app.route('/transactions/new', methods=['POST'])
def new_transaction():
    values = request.get_json()

    # Check that the required fields are in the POST'ed data
    required = ['sender', 'recipient', 'amount']
    if not all(k in values for k in required):
        return 'Missing values', 400

    # Creater a new Transaction
    index = blockchain.new_transaction(values['sender'],
                                       values['recipient'],
                                       values['amount'])
    response = {'message': f'Transaction will be added to Block {index}'}

    return jsonify(response), 201


# 完全なブロックチェーンを返す/chainエンドポイント
@app.route('/chain', methods=['GET'])
def full_chain():
    response = {
        'chain': blockchain.chain,
        'length': len(blockchain.chain),
    }
    return jsonify(response), 200

# 隣接するノード追加のためのエンドポイント
@app.route('/nodes/register', methods=['POST'])
def register_nodes():
    values = request.get_json()

    nodes = values.get('nodes')
    if nodes is None:
        return "Error: Please supply a valid list of nodes", 400

    for node in nodes:
        blockchain.register_node(node)

    response = {
        'message': 'New nodes have been added',
        'total_nodes': list(blockchain.nodes),
    }
    return jsonify(response), 201


# 矛盾を解決するためのエンドポイント
@app.route('/nodes/resolve', methods=['GET'])
def consensus():
    replaced = blockchain.resolve_conflicts()

    if replaced:
        response = {
            'message': 'Our chain was replaced',
            'new_chain': blockchain.chain
        }
    else:
        response = {
            'message': 'Our chain is authoritative',
            'chain': blockchain.chain
        }

    return jsonify(response), 200


# サーバをポート5000で実行
if __name__ == '__main__':
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument('-p', '--port', default=5000, type=int, help='port to listen on')
    args = parser.parse_args()
    port = args.port

    app.run(host='127.0.0.1', port=5000)
