"""Official PP-OCRv5 detection and recognition on local ONNX Runtime.

Model preprocessing and CTC dictionaries follow the pinned PaddlePaddle exports.
No document rotation, language dictionary, or text correction is applied.
"""
import fcntl
from functools import lru_cache
from hashlib import sha256
import math
from pathlib import Path
import urllib.error
import urllib.request
import uuid

from piu_timeline import ROOT
MODELS = {
    'ko': {'name':'korean_PP-OCRv5_mobile_rec_onnx',
           'revision':'5c6f574b8e2230adf4287b33e736d71b9fabd28e',
           'inference.onnx':'92f0b7785e64fc9090106a241cf4c1eb97472824558272751b88a2a4476d3a08',
           'inference.yml':'f757fa1c40e99edcf27e9cce879b93eb2a51fa46f5ef39095689b8c37dd75998'},
    'en': {'name':'en_PP-OCRv5_mobile_rec_onnx',
           'revision':'3fafbc3b5dcf93dd72add9f48368be8a3a2cd33b',
           'inference.onnx':'b5f833dfc5d0eb71da397b4efa06ebeee9b431b690a47d6af40d77d8eabc557f',
           'inference.yml':'27e91d0582f40168aa218303c76e184bc78fa7a5d105aad0cfbad8458b441067'},
    'det': {'name':'PP-OCRv5_mobile_det_onnx',
            'revision':'e6f4fa85f00e168c862bc462aebca69eef9b3d3d',
            'inference.onnx':'a431985659dc921974177a95adcfbb90fd9e51989a5e04d70d0b75f597b6e61d',
            'inference.yml':'98069072e1b6b37d727fd9d9f11725faa46d6ea0de012f2ed26caea011c37699'},
}
PIPELINE = {'schema':1,'models':{key:value['revision'] for key,value in MODELS.items()},
            'preprocessing':'paddle-bgr-48-ctc-db960-v1'}


def model_files(language):
    model=MODELS[language]
    directory=ROOT/'.local/cache/paddleocr'/language
    directory.mkdir(parents=True,exist_ok=True)
    with (directory/'.download.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        for filename in ('inference.onnx','inference.yml'):
            path=directory/filename
            if path.is_file() and sha256(path.read_bytes()).hexdigest()==model[filename]:
                continue
            temporary=directory/(filename+'.'+uuid.uuid4().hex+'.part')
            url=f"https://huggingface.co/PaddlePaddle/{model['name']}/resolve/{model['revision']}/{filename}"
            try:
                with urllib.request.urlopen(url,timeout=60) as response,temporary.open('wb') as stream:
                    while block:=response.read(1024*1024):stream.write(block)
                if sha256(temporary.read_bytes()).hexdigest()!=model[filename]:
                    raise ValueError(f'PaddleOCR model checksum mismatch: {filename}')
                temporary.replace(path)
            except (OSError,urllib.error.URLError) as error:
                raise ValueError(f'Could not download PaddleOCR {language} model: {error}') from error
            finally:
                temporary.unlink(missing_ok=True)
    return directory


def providers(device, available):
    if device=='mps':
        raise ValueError('PaddleOCR ONNX does not support PIU_OCR_DEVICE=mps; use auto, cpu or native Vision')
    if device.startswith('cuda') or device=='auto' and 'CUDAExecutionProvider' in available:
        if 'CUDAExecutionProvider' not in available:
            raise ValueError('CUDA OCR requires onnxruntime-gpu; use PIU_OCR_DEVICE=auto for CPU fallback')
        index=int(device.split(':')[1]) if ':' in device else 0
        return [('CUDAExecutionProvider',{'device_id':index}),'CPUExecutionProvider']
    return ['CPUExecutionProvider']


def prepare_crop(image):
    import cv2
    import numpy as np
    height,width=image.shape[:2]
    if min(height,width)<1:raise ValueError('Empty OCR text crop')
    resized_width=max(1,min(8192,math.ceil(48*width/height)))
    normalized=cv2.resize(image,(resized_width,48)).astype('float32').transpose(2,0,1)/127.5-1
    tensor=np.zeros((1,3,48,max(320,resized_width)),dtype='float32')
    tensor[0,:,:,:resized_width]=normalized
    return tensor


def decode_ctc(probabilities, characters):
    import numpy as np
    indices=probabilities.argmax(axis=-1)
    scores=probabilities.max(axis=-1)
    text,confidence=[],[]
    previous=None
    for index,score in zip(indices,scores):
        if index and index!=previous:
            if index>=len(characters):raise ValueError('OCR model and character dictionary do not match')
            text.append(characters[index]);confidence.append(float(score))
        previous=index
    return ''.join(text),float(np.mean(confidence)) if confidence else 0.


@lru_cache(maxsize=4)
def recognizer(english,device):
    try:
        import onnxruntime as ort
        import yaml
    except ImportError as error:
        raise ValueError('Install OCR dependencies with .venv/bin/python -m pip install -r requirements.txt') from error
    directory=model_files('en' if english else 'ko')
    metadata=yaml.safe_load((directory/'inference.yml').read_text())
    characters=['']+metadata['PostProcess']['character_dict']+[' ']
    options=ort.SessionOptions()
    options.intra_op_num_threads=2;options.inter_op_num_threads=1;options.log_severity_level=3
    session=ort.InferenceSession(str(directory/'inference.onnx'),sess_options=options,
                                providers=providers(device,ort.get_available_providers()))
    return session,characters


@lru_cache(maxsize=4)
def detector(device):
    import onnxruntime as ort
    directory=model_files('det')
    options=ort.SessionOptions()
    options.intra_op_num_threads=2;options.inter_op_num_threads=1;options.log_severity_level=3
    return ort.InferenceSession(str(directory/'inference.onnx'),sess_options=options,
                                providers=providers(device,ort.get_available_providers()))


def ordered_box(points):
    import numpy as np
    sides=points[np.argsort(points[:,0])]
    left=sides[:2][np.argsort(sides[:2,1])];right=sides[2:][np.argsort(sides[2:,1])]
    return np.float32([left[0],right[0],right[1],left[1]])


def detect_boxes(image,device):
    """Paddle DB probability thresholding, polygon expansion and rescaling."""
    import cv2
    import numpy as np
    import pyclipper
    height,width=image.shape[:2]
    ratio=960/max(height,width)
    shape=(max(32,round(width*ratio/32)*32),max(32,round(height*ratio/32)*32))
    pixels=cv2.resize(image,shape).astype('float32')/255
    pixels=(pixels-np.float32([.485,.456,.406]))/np.float32([.229,.224,.225])
    session=detector(device)
    probability=session.run(None,{session.get_inputs()[0].name:pixels.transpose(2,0,1)[None]})[0][0,0]
    contours,_=cv2.findContours((probability>.3).astype('uint8'),cv2.RETR_LIST,cv2.CHAIN_APPROX_SIMPLE)
    boxes=[]
    for contour in contours[:1000]:
        rectangle=cv2.minAreaRect(contour)
        if min(rectangle[1])<3:continue
        points=cv2.boxPoints(rectangle)
        x0,y0=np.maximum(0,np.floor(points.min(axis=0)).astype(int))
        x1,y1=np.minimum(np.array(probability.shape[::-1])-1,np.ceil(points.max(axis=0)).astype(int))
        mask=np.zeros((y1-y0+1,x1-x0+1),dtype='uint8')
        cv2.fillPoly(mask,[np.rint(points-[x0,y0]).astype('int32')],1)
        if cv2.mean(probability[y0:y1+1,x0:x1+1],mask)[0]<.6:continue
        perimeter=cv2.arcLength(points,True)
        if not perimeter:continue
        offset=pyclipper.PyclipperOffset()
        offset.AddPath(np.rint(points*64).astype('int64').tolist(),pyclipper.JT_ROUND,pyclipper.ET_CLOSEDPOLYGON)
        expanded=offset.Execute(cv2.contourArea(points)*1.5/perimeter*64)
        if len(expanded)!=1:continue
        rectangle=cv2.minAreaRect(np.float32(expanded[0])/64)
        if min(rectangle[1])<5:continue
        box=ordered_box(cv2.boxPoints(rectangle))
        box*=np.float32([width/probability.shape[1],height/probability.shape[0]])
        box[:,0]=np.clip(box[:,0],0,width);box[:,1]=np.clip(box[:,1],0,height)
        boxes.append(box)
    return boxes


def recognize_crops(session,characters,crops):
    """Batch similarly sized lines without letting a long title pad every row."""
    import numpy as np
    prepared=sorted([(i,prepare_crop(crop)) for i,crop in enumerate(crops)],key=lambda pair:pair[1].shape[-1])
    results=[None]*len(crops)
    while prepared:
        batch=[prepared.pop(0)]
        while prepared and len(batch)<8 and prepared[0][1].shape[-1]*(len(batch)+1)<=4096:
            batch.append(prepared.pop(0))
        width=max(tensor.shape[-1] for _,tensor in batch)
        tensor=np.zeros((len(batch),3,48,width),dtype='float32')
        for row,(_,image) in enumerate(batch):tensor[row,:,:,:image.shape[-1]]=image[0]
        output=session.run(None,{session.get_inputs()[0].name:tensor})[0]
        for (index,_),probabilities in zip(batch,output,strict=True):
            results[index]=decode_ctc(probabilities,characters)
    return results


def read_image(path,english=False,device='auto',single_line=False):
    import cv2
    import numpy as np
    from piu_timeline.vision.ocr import normalized_line
    session,characters=recognizer(english,device)
    image=cv2.imread(str(path))
    if image is None:raise ValueError(f'Cannot read OCR image: {path}')
    height,width=image.shape[:2]
    if single_line:
        text,confidence=recognize_crops(session,characters,[image])[0]
        return ([{'text':text,'confidence':confidence,'box':[0.,0.,1.,1.],
                  'method':'known_text_region'}] if text.strip() else [])
    boxes,crops=[],[]
    for points in detect_boxes(image,device):
        points=np.asarray(points,dtype='float32')
        w=max(1,round(max(np.linalg.norm(points[1]-points[0]),np.linalg.norm(points[2]-points[3]))))
        h=max(1,round(max(np.linalg.norm(points[3]-points[0]),np.linalg.norm(points[2]-points[1]))))
        transform=cv2.getPerspectiveTransform(points,np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]))
        crop=cv2.warpPerspective(image,transform,(w,h),borderMode=cv2.BORDER_REPLICATE)
        boxes.append(points);crops.append(crop)
    lines=[]
    for points,(text,confidence) in zip(boxes,recognize_crops(session,characters,crops)):
        if text.strip():lines.append(normalized_line(points,text,confidence,width,height))
    return sorted(lines,key=lambda line:(line['box'][1],line['box'][0]))
