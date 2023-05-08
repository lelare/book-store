from concurrent import futures
import logging
import random
import threading
import time
import grpc
import messages_pb2 as book_pb2
import messages_pb2_grpc as book_pb2_grpc

from game_1 import Game

class Book(book_pb2_grpc.GameServicer):

    def __init__(self, id, next_node_address, game_obj = Game()):
            self.id = id
            self.next_node_address = next_node_address
            self.leader_id = -1
            self.timestamp = None        
            self.turn_player = None
            self.game = game_obj
            self.observers = dict()
            self.updates = {}

    def Election(self, request, context):
        if request.id < self.id:
            return book_pb2.ElectionResponse(id=self.id)
        elif request.id == self.id:
            self.leader_id = self.id
            self.timestamp = time.time()
            return book_pb2.ElectionResponse(id=self.id)
        else:
            with grpc.insecure_channel(self.next_node_address) as channel:
                stub = book_pb2_grpc.GameStub(channel=channel)
                response = stub.Election(request)
            if response.id != self.id:
                self.leader_id = response.id
                self.timestamp = time.time()
            return response

    def TimeSync(self, request, context):
        if self.leader_id != -1 and self.timestamp is not None:
            return book_pb2.TimeSyncResponse(id=self.leader_id, time=self.timestamp)
        else:
            return book_pb2.TimeSyncResponse(id=-1, time=0)

    def start_election(self):
        with grpc.insecure_channel(self.next_node_address) as channel:
            stub = book_pb2_grpc.GameStub(channel=channel)
            response = stub.Election(book_pb2.ElectionRequest(id=self.id))

        if response.id != self.id:
            print(f"Node {self.id} lost election to node {response.id}")
            self.leader_id = response.id
            self.timestamp = time.time()


    def connect(self, request, context):
        user_id = request.id
        self.observers[user_id] = context
        logging.info(f"Connecting user: {request.id}")
        response = book_pb2.PlayerResponse()
        response.count_of_users = self.observers.keys().__len__()
        return response

    def update(self, request_iterator, context):
        for req in request_iterator: 
            logging.info(f"Update request from {req.id}")
            copy_updates = self.updates.copy()
            if req.id in self.updates.keys():
                update = self.updates.pop(req.id)
                yield book_pb2.UpdateResponse(**update)
            else:
                yield book_pb2.UpdateResponse(changes=False)


def election_task(node, interval):
    random.seed(time.time())
    time.sleep(interval + random.uniform(1, 3))  # Add random delay before starting the election
    node.start_election()
        
def serve(id, next_node_address, port, leader_election_interval, game_obj):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    node = Book(id, next_node_address, game_obj)
    book_pb2_grpc.add_GameServicer_to_server(node, server)
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    print(f"Node {id} running on port {port}")

    # Start a separate thread for running leader election periodically
    election_thread = threading.Thread(target=election_task, args=(node, leader_election_interval))
    election_thread.daemon = True
    election_thread.start()

    return node, server

def main():
    game = Game()
    leader_election_interval = 3  # Time in seconds between leader elections
    node1, server1 = serve(1, "localhost:50052", 50051, leader_election_interval, game)
    node2, server2 = serve(2, "localhost:50053", 50052, leader_election_interval, game)
    node3, server3 = serve(3, "localhost:50054", 50053, leader_election_interval, game)
    node4, server4 = serve(4, "localhost:50051", 50054, leader_election_interval, game)

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        server1.stop(0)
        server2.stop(0)
        server3.stop(0)
        server4.stop(0)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main() 
