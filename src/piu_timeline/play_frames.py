"""Streaming native-frame decoding with original PTS; no FPS conversion."""
from collections import deque
from fractions import Fraction
import queue
import re
import subprocess
import threading

import numpy as np


def decode_frames(record, start, end, roi, width=650, region=None):
    x, y, w, h = roi
    height = max(1, round(width * h / w))
    filters = f'showinfo,crop={w}:{h}:{x}:{y},scale={width}:{height}'
    output_width, output_height = width, height
    if region is not None:
        rx,ry,rw,rh = region
        left,top = int(rx*width),int(ry*height)
        output_width,output_height = int((rx+rw)*width)-left,int((ry+rh)*height)-top
        filters += f',format=rgb24,crop={output_width}:{output_height}:{left}:{top}:exact=1'
    command = ['ffmpeg', '-hide_banner', '-v', 'info', '-nostdin', '-ss', str(start),
               '-t', str(end - start), '-copyts', '-noautorotate', '-i', record['path'],
               '-map', f"0:{record['video_streams'][0]['index']}",
               '-vf', filters,
               '-fps_mode', 'passthrough', '-pix_fmt', 'rgb24', '-an', '-f', 'rawvideo', 'pipe:1']
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    timestamps, errors = queue.Queue(), deque(maxlen=12)
    def read_info():
        time_base = None
        for raw in process.stderr:
            line = raw.decode('utf-8', errors='replace')
            errors.append(line.strip())
            match = re.search(r'config in time_base:\s*(\d+/\d+)', line)
            if match:
                time_base = Fraction(match.group(1))
            match = re.search(r'\bn:\s*\d+\s+pts:\s*(-?\d+)\s+pts_time:', line)
            if match and time_base is not None:
                timestamps.put(float(int(match.group(1)) * time_base))
        timestamps.put(None)
    thread = threading.Thread(target=read_info, daemon=True)
    thread.start()
    size, last = output_width * output_height * 3, None
    try:
        while True:
            data = bytearray()
            while len(data) < size:
                chunk = process.stdout.read(size - len(data))
                if not chunk:
                    break
                data.extend(chunk)
            if not data:
                break
            if len(data) != size:
                raise ValueError('Truncated decoded frame')
            try:
                pts = timestamps.get(timeout=30)
            except queue.Empty as error:
                raise ValueError('Timed out waiting for source frame PTS') from error
            if pts is None:
                raise ValueError('Decoded frame has no original PTS')
            playback = pts - record['container_start_seconds']
            if last is not None and pts <= last:
                raise ValueError('Non-increasing source frame PTS; timing analysis requires distinct frames')
            last = pts
            if start - .000001 <= playback < end:
                yield pts, playback, np.frombuffer(data, dtype='uint8').reshape(output_height, output_width, 3)
        if process.wait():
            raise ValueError('Frame decoding failed: ' + '\n'.join(errors))
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
        thread.join(timeout=5)
        process.stdout.close(); process.stderr.close()


def crop_region(rgb, region):
    height, width = rgb.shape[:2]
    x, y, w, h = region
    return rgb[int(y * height):int((y + h) * height), int(x * width):int((x + w) * width)]
