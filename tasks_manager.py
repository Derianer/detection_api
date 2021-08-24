#!/opt/detection_server/.env/bin/python
"""Manager that recives tasks from server and scedule it`s to redis queue"""
import sys
import re
import warnings
import logging
import asyncio
import aiohttp
from typing import Any, Dict
from dataclasses import dataclass
from aiohttp import web
import rq
from rq import Queue, Worker
from rq.command import send_stop_job_command
from rq.job import Job
from redis import Redis, RedisError
from detect_cards import detect_cards_task


logging.basicConfig(filename='manager_log.log', level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))



class MissingTaskError(Exception):
    pass

"""Dataclass that represents task object structure."""
@dataclass
class RecognitionTask:
    func: Any
    data: Any
    job: Any = None
    result: Any = None

"""TasksQueue implement adding task to redis queue. Also incapsulates redis connectinon,
 and check for existing workers."""
class TasksQueue:

    def __init__(self, queue_name='default', host='localhost', port=6379):
        try:
            self._redis_conn = Redis()
        except RedisError as redis_err:
            print(redis_err)
        else:
            self._check_for_workers()
            self._redis_queue = Queue(name=queue_name, connection=self._redis_conn, default_timeout=1000)
            self._enqueued_tasks = {}

    def _check_for_workers(self):
        self._workers = Worker.all(connection=self._redis_conn)
        if len(self._workers) == 0:
            logging.info("No workers found, card detection can not be carried out")
            warnings.warn("No workers found, card detection can not be carried out") 
        #assert len(self._workers) != 0, "No workers found"

    def add_task(self, task: RecognitionTask):
        # task.job = Job.create(func=task.func, args=task.data, result_ttl=10)
        task.job = self._redis_queue.enqueue(task.func, **(task.data))
        self._enqueued_tasks[task.job.id] = task
        return task.job.id

    async def ret_complited_task(self, waited_task_id, timeout=1) -> RecognitionTask: 
        while True:
            self._check_for_workers()
            try:
                task = self._enqueued_tasks[waited_task_id]
            except KeyError:
                raise MissingTaskError(f"Task {waited_task_id} does not exists")
            else:
                if task.job.is_finished:
                    task.result = task.job.result
                    task.job = None
                    self._enqueued_tasks.pop(waited_task_id)
                    return task
                if task.job.is_failed:
                    task.result = False
                    task.job = None
                    self._enqueued_tasks.pop(waited_task_id)
                    return task
                await asyncio.sleep(timeout)
    
    def remove_task(self, task_id) -> None:
        try:
            job = self._enqueued_tasks.pop(task_id).job
            try:
                send_stop_job_command(self._redis_conn, job.id)
            except:
                pass
            try:
                self._redis_queue.scheduled_job_registry.remove(job.id, delete_job=True)
            except:
                pass
            try:
                self._redis_queue.started_job_registry.remove(job.id, delete_job=True)
            except:
                pass
            try:
                self._redis_queue.deferred_job_registry.remove(job.id, delete_job=True)
            except:
                pass
            logging.info(f"Task {task_id} was removed from queue")
        except KeyError:
            raise MissingTaskError(f"Task {task_id} does not exists")

class JSONFormatError(Exception):
    pass

class RecognizeError(Exception):
    pass
    
"""TasksHandler implements api that server connecting to"""
class TasksHandler:

    def __init__(self):
        self._app = web.Application()
        self._tasks_queues = {}
        self._set_handlers()
        self._create_tasks_queues()

    def run_handler(self, host, port):
        web.run_app(self._app, host=host, port=port)

    def _create_tasks_queues(self, *queue_names):
        if len(queue_names) == 0:
            self._tasks_queues['default'] = TasksQueue(queue_name='default')
        else:
            for name in queue_names:
                self._tasks_queues[name] = TasksQueue(queue_name=name)

    def _set_handlers(self):
        self._app.add_routes([web.post('/api/image/recognize', self._handle_task)])

    async def _handle_task(self, request: web.Request):
        "Handle server post request and enqueues task to redis queue"
        try:
            data = await self._extract_data_form_req(request)
            rec_task = RecognitionTask(detect_cards_task, data)
            task_id = self._add_task_to_queue('default', rec_task)
            task = await self._tasks_queues['default'].ret_complited_task(task_id)
            if task.result != False:
                js_obj = {'result':task.result}
                return web.json_response(js_obj)
            raise RecognizeError("Fail to recognize")
        except asyncio.TimeoutError as error:
            self._tasks_queues['default'].remove_task(task_id)
            logging.error(str(error))
            raise web.HTTPInternalServerError(reason=str(error))
        except asyncio.CancelledError as error:
            self._tasks_queues['default'].remove_task(task_id)
            logging.error(str(error))
            raise web.HTTPInternalServerError(reason=str(error))
        except BaseException as error:
            self._tasks_queues['default'].remove_task(task_id)
            logging.error(str(error))
            raise web.HTTPInternalServerError(reason=str(error))
        except Exception as error:
            logging.error(str(error))
            raise web.HTTPInternalServerError(reason=str(error))
    
    def _add_task_to_queue(self, queue_name, task):
        """Returns id of added task"""
        return self._tasks_queues[queue_name].add_task(task)

    async def _extract_data_form_req(self, req: web.Request):
        if req.content_type == 'application/json':
            try:
                js = await req.json()
                text = await req.text()
                print(text)
                data = await self._get_image_request(req.remote, js['url'])
                return data
            except KeyError:
                raise JSONFormatError("Wrong json keys")
        elif req.content_type == 'multipart/form-data':
            return await self._read_multipart(req)
        else:
            raise web.HTTPUnsupportedMediaType(reason='Type: ' \
                                            + req.content_type \
                                            + " is not supported")
    
    async def _read_multipart(self, request:web.Request):
        image_reader = await request.multipart()
        request_data = {}
        part = await image_reader.next()
        while part is not None:
            data = await self._recive_data_from_stream_reader(part)
            try:
                content_disp = part.headers[aiohttp.hdrs.CONTENT_DISPOSITION]
                if content_disp.find("image") > 0:
                    request_data['image'] = data
                elif content_disp.find("spread") > 0:
                    request_data['spread'] = data.decode('utf-8')
                elif content_disp.find("id") > 0:
                    request_data['id'] = data.decode('utf-8')
                else:
                    request_data['else'] = data
            except Exception as err:
                logging.error(str(err))
            logging.info(part.headers[aiohttp.hdrs.CONTENT_DISPOSITION])
            part = await image_reader.next()
        try:
            logging.info(f"spread = {request_data['spread']}")
            logging.info(f"id = {request_data['id']}")
        except:
            pass
        return request_data

    async def _get_image_request(self, adress, path):
        """send get request to 'adress' to get image"""
        async with aiohttp.ClientSession() as session:
            full_adress = f'http://{adress}:80{path}'
            print (f'req to {full_adress}')
            async with session.get(full_adress) as resp:
                data_reader = resp.content
                image = await self._recive_data_from_stream_reader(data_reader)
                return image

    async def _recive_data_from_stream_reader(self, stream_reader):
        try:
            data = b""
            async for recived_data in stream_reader:
                data += recived_data
            # logging.debug(data.decode('utf-8'))
            return data    
        except aiohttp.StreamReader().exception():
            raise web.HTTPNoContent(reason='Can`t read content')

def main():
    """App starting point"""
    handler = TasksHandler()
    handler.run_handler(host='127.0.0.1', port=8080)

if __name__ == '__main__':
    main()
