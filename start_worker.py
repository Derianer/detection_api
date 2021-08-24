#!/opt/detection_server/.env/bin/python
import logging
import sys
from rq import Queue, SimpleWorker
from redis import Redis


class DetectionWorker(SimpleWorker):

    def __init__(self, *args, **kwargs):
        SimpleWorker.__init__(self, *args, **kwargs)


    def execute_job(self, job, queue):
        return self.perform_job(job, queue)

if __name__ == "__main__":
    redis_con = Redis()
    queue = Queue(connection=redis_con)
    worker = DetectionWorker(queues=[queue], connection=redis_con)
    logging.basicConfig(filename='worker.log', level=logging.INFO)
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
    worker.work()
