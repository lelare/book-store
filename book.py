import logging
import time
import uuid
from grpc import RpcError
import grpc
from messages_pb2 import ConnectionRequest, UpdateRequest, TimeSyncRequest
from messages_pb2_grpc import GameStub
import threading
import platform
import multiprocessing
import random


class GameComponent:
    def __init__(self, game):
        self.client = game
        self.user = str(uuid.uuid4())
        self.processes = []
        self.book_prices = {}

    def connect_to_server(self):
        try:
            resp = self.client.connect(ConnectionRequest(id=self.user))
        except RpcError as e:
            raise Exception(f"Error connecting to server: {e.details()}")
        if resp.count_of_users == 0:
            raise Exception("Error")
        
    def handle_updates(self):
        while True: 
            def request_generator():
                    yield UpdateRequest(id=self.user)
            response = None
            try:
                response = next(self.client.update(request_generator()))
            except Exception as e:
                print(f"Exception occurred: {e}")
            if response is None or response.changes == False:
                time.sleep(5)
                continue
            if response.message is not None in response.message:
                print(response.message)
                break
            time.sleep(5)

    # 1) Local-store-ps:
    def create_store_ps(self, k):
        node = platform.node()

        for i in range(k):
            psID = f"{node}-ps{i+1}"
            process = multiprocessing.Process(target=self.data_store_ps, args=(psID,))
            self.processes.append(process)
            process.start()

    def data_store_ps(psID):
        print(f"Data store process {psID} created.")

    # 2) Create-chain:
    def create_chain(self):
        if self.processes:
            print("Error: replication chain already exists.")
            choice = input("Enter 'y' to recreate the chain or any other key to continue: ")
            if choice.lower() != "y":
                return

        random.shuffle(self.processes)
        head = self.processes[0]
        tail = self.processes[-1]

        for i in range(len(self.processes)-1):
            self.processes[i].successor = self.processes[i+1]
            self.processes[i+1].predecessor = self.processes[i]

        print("Replication chain created successfully")
        # print(f"Head: {head}")
        # print(f"Tail: {tail}")

    # 3) List-chain:
    def list_chain(self):
        if not self.processes:
            print("Error: replication chain does not exist yet.")
            return

        for i, process in enumerate(self.processes):
            print(f"Process {i}: {process}")
            if process.predecessor:
                print(f"Predecessor: {process.predecessor}")
            if process.successor:
                print(f"Successor: {process.successor}")
            print()

        head = self.processes[0]
        tail = self.processes[-1]
        print(f"Head: {head}")
        print(f"Tail: {tail}")

    # 4) Write-operation <“Book”, Price>:
    def set_book_price(self, bookName, price):
        update_request = UpdateRequest(user=self.user, data=f"{bookName},{price}")
        try:
            self.client.update(update_request)
            self.book_prices[bookName] = price
            print(f"{bookName} = {price} EUR")
        except RpcError as e:
            print(f"Error writing book price: {e}")

    # 5) List-books:
    def list_books(self):
        books = list(self.book_prices.keys())
        if not books:
            print("No books available.")
        else:
            for book in books:
                print(f"{book} = {self.book_prices[book]} EUR")


    # 6) Read-operation:
    def get_book_price(self, bookName):
        for process in self.processes:
            try:
                stub = GameStub(grpc.insecure_channel(process))
                response = stub.GetPrice(ConnectionRequest(data=bookName))
                if response.success:
                    print(f"{response.data} EUR")
                    return
            except Exception as e:
                print(f"Error: {e}")
        print(f"Not yet in the stock")


    def run(self, k):
        self.connect_to_server()
        thread = threading.Thread(target=self.handle_updates, daemon=True)
        thread.start()
        while True:
            option = input("Enter '1' to create chain, '2' to list chain, '3' for add <Book, Price>, '4' to list books, '5' to get book price or '0' to exit: ")
            if option == '0':
                thread.join()
                break
            elif option == '1':
                self.create_store_ps(k)
                self.create_chain()
            elif option == '2':
                self.list_chain()
            elif option == '3':
                bookName = input("Enter book name: ")
                bookPrice = float(input("Enter price: "))
                self.set_book_price(bookName, bookPrice)
            elif option == '4':
                self.list_books()
            elif option == '5':
                bookName = input("Enter book name to get its price: ")
                self.get_book_price(bookName)
            else:
                print("Invalid option. Please enter '1', '2', '3', '4', '5', or '0'.")



def query_node(address):
    with grpc.insecure_channel(address) as channel:
        stub = GameStub(channel)
        response = stub.TimeSync(TimeSyncRequest())
        print(f"response: {response}")
    if response.id != -1:
        return response.id, response.time, address
    else:
        return None, None, None

def main():
    node_addresses = ['localhost:50052', 'localhost:50051', 'localhost:50053', "localhost:50054"]
    leader_id, leader_time, address = None, None, None
    while True:
        for address in node_addresses:
            print(f"Querying node at {address}...")
            leader_id, leader_time, address = query_node(address)
            if leader_id is not None:                
                break

        if leader_id is not None:
                print(f"Node at {address} reports leader: Node {leader_id} with timestamp {leader_time}")
                break
        else:
            print(f"Node at {address} reports no leader elected yet.")
        time.sleep(5)
    channel = grpc.insecure_channel(address)
    game = GameComponent(GameStub(channel))
    # game.run()
    k = int(input('Enter number of k processes (0 to exit): '))
    game.run(k=k)


if __name__ == '__main__':
    main()