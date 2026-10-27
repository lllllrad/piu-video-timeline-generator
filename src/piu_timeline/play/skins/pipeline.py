"""Bounded, ordered frame detection; tracking and source PTS stay in the parent."""
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
import os

import cv2

from piu_timeline.play.skins.detector import SkinDetector

_detector = None


def worker_count():
    available=len(os.sched_getaffinity(0))if hasattr(os,'sched_getaffinity')else(os.cpu_count()or 1)
    configured=os.environ.get('PIU_SKIN_JOBS')
    try:jobs=int(configured)if configured is not None else min(8,max(1,available//2))
    except ValueError as error:raise ValueError('PIU_SKIN_JOBS must be an integer from 1 to 32')from error
    if not 1<=jobs<=32:raise ValueError('PIU_SKIN_JOBS must be an integer from 1 to 32')
    return jobs


def initialize_worker(bank,layout,width,height):
    global _detector
    cv2.setNumThreads(1)
    _detector=SkinDetector(bank,layout,width,height)


def detect_frame(rgb):
    return _detector.detect(rgb)


def _classified_frames(frames,bank,layout,width,height,jobs):
    """Keep at most two original RGB frames per worker in flight.

    Workers receive one frozen bank and return detections only. The original
    image object, source PTS and playback time remain paired in the parent.
    Awaiting futures in submission order prevents completion order from
    changing trajectories or counter crops. Spawn avoids inherited CV threads.
    """
    if bank is None:
        for frame in frames:yield (*frame,None)
        return
    jobs=worker_count()if jobs is None else jobs
    if type(jobs)is not int or not 1<=jobs<=32:raise ValueError('Skin workers must be 1..32')
    if jobs==1:
        detector=SkinDetector(bank,layout,width,height)
        for pts,time,rgb in frames:yield pts,time,rgb,detector.detect(rgb)
        return
    # Validate image-bank geometry before starting child processes.
    SkinDetector(bank,layout,width,height)
    pending=deque()
    with ProcessPoolExecutor(max_workers=jobs,mp_context=get_context('spawn'),
            initializer=initialize_worker,initargs=(bank,layout,width,height))as executor:
        try:
            for frame in frames:
                pending.append((frame,executor.submit(detect_frame,frame[2])))
                if len(pending)>=2*jobs:
                    original,future=pending.popleft();yield (*original,future.result())
            while pending:
                original,future=pending.popleft();yield (*original,future.result())
        finally:
            for _,future in pending:future.cancel()


def classified_frames(frames,bank,layout,width,height,jobs=None):
    """Return ordered detections and close acquisition on completion or failure."""
    try:
        yield from _classified_frames(frames,bank,layout,width,height,jobs)
    finally:
        if hasattr(frames,'close'):frames.close()
