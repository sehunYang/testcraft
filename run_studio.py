from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).parent/'.runtime/packages'))
from app.server import serve

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    serve(parser.parse_args().port)
