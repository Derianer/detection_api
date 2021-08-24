import time
import logging
from taro_detection.detect import detector
import os

def detect_cards_task(*args, **kwargs):
    try:
        start = time.time()
        abspath = os.path.abspath(__file__)
        dname = os.path.dirname(abspath)
        image_dir_name = dname+f'/images/{kwargs["spread"]}'
        if not os.path.exists(image_dir_name):
            os.makedirs(image_dir_name)
        image_path = image_dir_name + f"/{kwargs['id']}.jpg"
        try:
            with open(image_path, 'wb') as saved_file:
                saved_file.write(kwargs["image"])
        except Exception as err:
            logging.error(str(err))
            logging.error('Fail to save image')
    except KeyError as err:
        logging.error(repr(err))
        logging.error(f"Wrong arguments recived: {[key for key in kwargs.keys()]}")
    try:
        detection_res = detector(source=image_path,\
                                 **{key:value for key, value in kwargs.items() if key in detector.__code__.co_varnames})
        end = time.time()
        det_time = 'Detection time = ' + str(end - start)
    except Exception as err:
        logging.error(str(repr(err)))
        logging.error(f"Fail to recognize:id = {kwargs['id']}, spread = {kwargs['spread']}")
        return False
    else:
        det_res = f'Detecton result: {detection_res}' 
        logging.info(det_time)
        logging.info(det_res)
        return detection_res
    return False
