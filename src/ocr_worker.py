"""Run OCR in the bundled x64 interpreter; videos stay in the app process."""
import base64
import json
import os
import sys
import threading

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')


def send(value):
    print('ARCADECLIP_OCR ' + json.dumps(value, ensure_ascii=True), flush=True)


def main():
    try:
        from PIL import Image
        from text_recognition import make_ocr
        read = make_ocr(sys.argv[1], threading.Event(), lambda message: send({'progress': message}), _local=True)
        send({'ready': True})
        for line in sys.stdin:
            request = json.loads(line)
            image = Image.frombytes('RGB', tuple(request['size']), base64.b64decode(request['pixels'], validate=True))
            text, score = read(image)
            send({'text': text, 'score': float(score)})
    except Exception as error:
        send({'error': f'{type(error).__name__}: {error}'})
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
