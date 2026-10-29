"""Lossless synthetic source video through the real native decoder."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from piu_timeline.play.frames import decode_frames
from piu_timeline.tools.timeline import media_record


def encoded(images,fps,root,width):
    h,w=images[0].shape[:2]
    with tempfile.TemporaryDirectory(dir=root)as tmp:
        video=Path(tmp)/'source.nut'
        subprocess.run(['ffmpeg','-v','error','-nostdin','-n','-f','rawvideo','-pixel_format','rgb24',
                        '-video_size',f'{w}x{h}','-framerate',str(fps),'-i','pipe:0','-c:v','ffv1',
                        '-output_ts_offset','42.125',str(video)],input=b''.join(i.tobytes()for i in images),check=True,capture_output=True)
        before=hashlib.sha256(video.read_bytes()).hexdigest(),video.stat().st_mtime_ns
        probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
             '-show_entries','stream=time_base:frame=pts','-of','json',str(video)],text=True))
        base=Fraction(probe['streams'][0]['time_base'])
        expected_pts=[float(f['pts']*base)for f in probe['frames']]
        record=media_record(video)
        observed=list(decode_frames(record,0,len(images)/fps,[0,0,w,h],width))
        preserved=before==(hashlib.sha256(video.read_bytes()).hexdigest(),video.stat().st_mtime_ns)
        return observed,expected_pts,preserved
