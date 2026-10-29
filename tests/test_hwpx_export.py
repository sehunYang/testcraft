"""Mocked HWPX export lifecycle tests; these tests never launch Hancom COM."""
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'.runtime/packages'))
from app import core, server
from app.hwpx import validate_hwpx_package
from test_support import cleanup_tempdir
from test_workflow import card


def fake_hwpx(path,source_hml=None,*,keep_equations=True,keep_pictures=True):
    equations=pictures=0
    source_text=''
    if source_hml is not None:
        root=ET.parse(source_hml).getroot()
        nodes=list(root.iter())
        equations=sum(node.tag.rsplit('}',1)[-1].lower()=='equation' for node in nodes)
        pictures=sum(node.tag.rsplit('}',1)[-1].lower() in ('picture','pic') for node in nodes)
        source_text=''.join(node.text or '' for node in nodes if node.tag.rsplit('}',1)[-1].lower()=='char')
        if not keep_equations: equations=0
        if not keep_pictures: pictures=0
    body=ET.Element('sec')
    paragraph=ET.SubElement(body,'p')
    run=ET.SubElement(paragraph,'run')
    ET.SubElement(run,'t').text=source_text or '모의 변환 본문'
    for _ in range(equations): ET.SubElement(paragraph,'equation')
    for _ in range(pictures): ET.SubElement(paragraph,'pic')
    path=Path(path)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('mimetype','application/hwp+zip',compress_type=zipfile.ZIP_STORED)
        archive.writestr('Contents/content.hpf','<package/>')
        archive.writestr('Contents/section0.xml',ET.tostring(body,encoding='unicode'))


class HwpxExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'.runtime')
        self.data_patch=patch.object(core,'DATA',Path(self.tmp.name)/'studio')
        self.data_patch.start()
        item=card()
        item['question']=r'가속도 $a$로 운동할 때 $v=v_0+at$이다. 속도는?'
        self.exam=core.save_exam({'id':core.uid(),'title':'HWPX 출력 확인','subject':'12역학',
            'cards':[item],'exports':[],'revision':0,
            'card_approval':{'digest':core.cards_digest([item])}})

    def tearDown(self):
        self.data_patch.stop()
        cleanup_tempdir(self.tmp)

    @staticmethod
    def successful_process(command,**kwargs):
        args=command[3:]
        for source,destination in zip(args[0::2],args[1::2]):
            fake_hwpx(destination,source)
        return SimpleNamespace(returncode=0,stdout='모의 변환 성공',stderr='')

    def export_with_mock_converter(self):
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=self.successful_process) as run:
            bundle=server.export_exam(self.exam)
        return bundle,run

    def store_bundle(self,bundle):
        exam=core.read_exam(self.exam['id'])
        exam['exports'].append(bundle)
        self.exam=core.save_exam(exam)

    def test_export_and_recalculate_return_current_validation_and_digest(self):
        # The download UI must immediately recognize successful output without
        # reloading the page; plain save_exam records lack these derived fields.
        bundle={'id':core.uid(),'created':core.now(),'revision':self.exam['revision'],
                'content_digest':core.export_digest(self.exam),
                'conversion':{'status':'ready','message':'완료'},
                'files':list(server.EXPORT_DOCUMENTS)}
        for path in ('/api/export','/api/recalculate'):
            body=json.dumps({'exam_id':self.exam['id'],'revision':self.exam['revision'],
                             'export_id':bundle['id']}).encode()
            class MemoryHandler(server.Handler):
                def __init__(self):
                    self.path=path
                    self.headers={'Host':'127.0.0.1','X-Studio-Token':server.TOKEN,'Content-Length':str(len(body))}
                    self.rfile=io.BytesIO(body);self.wfile=io.BytesIO();self.status=None
                def send_response(self,status,message=None):self.status=status
                def send_header(self,*args):pass
                def end_headers(self):pass
            handler=MemoryHandler()
            with patch.object(server,'export_exam',return_value=bundle),patch.object(server,'recalculate_export'):
                handler.do_POST()
            self.assertEqual(handler.status,200)
            result=json.loads(handler.wfile.getvalue())
            self.assertTrue(result['validation']['ready'])
            self.assertEqual(result['content_digest'],result['exports'][-1]['content_digest'])
            self.assertTrue(result['cards_approved'])
            self.exam=result

    def test_automatic_conversion_publishes_valid_pair_and_complete_zip(self):
        bundle,run=self.export_with_mock_converter()
        self.assertEqual(bundle['conversion']['status'],'ready')
        self.assertEqual(run.call_count,1)
        self.assertIn('시험지_학생용.hwpx',bundle['files'])
        self.assertIn('시험지_교사용.hwpx',bundle['files'])
        self.assertIn('정답과해설.hwpx',bundle['files'])
        self.assertNotIn('정답과해설.md',bundle['files'])
        self.assertIn('출제결과.zip',bundle['files'])
        self.assertFalse(any(name.endswith('.hml') for name in bundle['files']))
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        self.assertTrue((folder/'시험지_학생용.hml').is_file())
        self.assertTrue((folder/'시험지_교사용.hml').is_file())
        self.assertTrue((folder/'정답과해설.hml').is_file())
        audit=json.loads((folder/'검수기록.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['conversion'],bundle['conversion'])
        with zipfile.ZipFile(folder/'출제결과.zip') as archive:
            expected=set(server.EXPORT_DOCUMENTS+server.EXPORT_SUPPORT_FILES)
            self.assertEqual(set(archive.namelist()),expected)
            self.assertIsNone(archive.testzip())

    def test_unavailable_conversion_keeps_internal_sources_and_omits_zip(self):
        with patch.object(server,'hwp_conversion_available',return_value=False), \
             patch.object(server.subprocess,'run') as run:
            bundle=server.export_exam(self.exam)
        self.assertEqual(bundle['conversion']['status'],'unavailable')
        self.assertFalse(run.called)
        self.assertNotIn('출제결과.zip',bundle['files'])
        self.assertFalse(any(name.endswith('.hwpx') for name in bundle['files']))
        self.assertFalse(any(name.endswith('.hml') for name in bundle['files']))
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        self.assertTrue((folder/'시험지_학생용.hml').is_file())
        self.assertTrue((folder/'시험지_교사용.hml').is_file())

    def test_package_validation_checks_equation_and_picture_retention(self):
        folder=Path(self.tmp.name)
        source=folder/'source.hml'
        source.write_text('<HWPML><CHAR>물체의 이동</CHAR><EQUATION/><PICTURE/></HWPML>',encoding='utf-8')
        valid=folder/'valid.hwpx'
        fake_hwpx(valid,source)
        result=validate_hwpx_package(valid,source)
        self.assertEqual((result['equations'],result['pictures']),(1,1))
        no_equation=folder/'no-equation.hwpx'
        fake_hwpx(no_equation,source,keep_equations=False)
        with self.assertRaisesRegex(ValueError,'수식'):
            validate_hwpx_package(no_equation,source)
        no_picture=folder/'no-picture.hwpx'
        fake_hwpx(no_picture,source,keep_pictures=False)
        with self.assertRaisesRegex(ValueError,'그림'):
            validate_hwpx_package(no_picture,source)

    def test_second_conversion_failure_never_publishes_first_half(self):
        def fail_teacher(command,**kwargs):
            args=command[3:]
            fake_hwpx(args[1],args[0])
            return SimpleNamespace(returncode=1,stdout='학생용 완료',stderr='교사용 변환 실패')
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=fail_teacher):
            bundle=server.export_exam(self.exam)
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        self.assertEqual(bundle['conversion']['status'],'failed')
        self.assertFalse((folder/'시험지_학생용.hwpx').exists())
        self.assertFalse((folder/'시험지_교사용.hwpx').exists())
        self.assertFalse((folder/'출제결과.zip').exists())
        self.assertTrue((folder/'시험지_학생용.hml').is_file())
        self.assertTrue((folder/'시험지_교사용.hml').is_file())

    def test_second_file_promotion_failure_rolls_back_pair(self):
        original_replace=server.os.replace
        def fail_teacher_promotion(source,destination):
            if Path(destination).name=='시험지_교사용.hwpx' and Path(source).name.startswith('.hwpx-'):
                raise OSError('교사용 파일 승격 실패')
            return original_replace(source,destination)
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=self.successful_process), \
             patch.object(server.os,'replace',side_effect=fail_teacher_promotion):
            bundle=server.export_exam(self.exam)
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        self.assertEqual(bundle['conversion']['status'],'failed')
        self.assertFalse((folder/'시험지_학생용.hwpx').exists())
        self.assertFalse((folder/'시험지_교사용.hwpx').exists())
        self.assertFalse((folder/'출제결과.zip').exists())

    def test_recalculate_retries_both_outputs_and_refreshes_zip_through_api(self):
        with patch.object(server,'hwp_conversion_available',return_value=False):
            bundle=server.export_exam(self.exam)
        self.store_bundle(bundle)
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        stale=folder/'출제결과.zip'
        stale.write_bytes(b'stale zip')
        request={'exam_id':self.exam['id'],'revision':self.exam['revision'],'export_id':bundle['id']}
        encoded=json.dumps(request).encode()

        class MemoryHandler(server.Handler):
            def __init__(inner):
                inner.path='/api/recalculate'
                inner.headers={'Host':'127.0.0.1','X-Studio-Token':server.TOKEN,
                               'Content-Length':str(len(encoded))}
                inner.rfile=io.BytesIO(encoded);inner.wfile=io.BytesIO();inner.status=None
            def send_response(inner,status,message=None): inner.status=status
            def send_header(inner,key,value): pass
            def end_headers(inner): pass

        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=self.successful_process) as run:
            handler=MemoryHandler();handler.do_POST()
        self.assertEqual(handler.status,200)
        self.assertEqual(run.call_count,1)
        saved=core.read_exam(self.exam['id'])
        refreshed=next(item for item in saved['exports'] if item['id']==bundle['id'])
        self.assertEqual(refreshed['conversion']['status'],'ready')
        self.assertIn('출제결과.zip',refreshed['files'])
        with zipfile.ZipFile(stale) as archive:
            self.assertEqual(set(archive.namelist()),set(server.EXPORT_DOCUMENTS+server.EXPORT_SUPPORT_FILES))
            self.assertIsNone(archive.testzip())
        audit=json.loads((folder/'검수기록.json').read_text(encoding='utf-8'))
        self.assertEqual(audit['conversion'],refreshed['conversion'])

    def test_failed_retry_preserves_last_good_hwpx_zip_and_audit(self):
        bundle,_=self.export_with_mock_converter()
        self.store_bundle(bundle)
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        protected=[*server.EXPORT_DOCUMENTS,server.EXPORT_ARCHIVE,'검수기록.json']
        original={name:(folder/name).read_bytes() for name in protected}
        exam=core.read_exam(self.exam['id'])
        def failed_process(command,**kwargs):
            return SimpleNamespace(returncode=1,stdout='학생용 완료',stderr='교사용 저장 실패')
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=failed_process):
            refreshed=server.recalculate_export(exam,bundle['id'])
        self.assertEqual(refreshed['conversion']['status'],'ready')
        self.assertIn('retry_error',refreshed['conversion'])
        self.assertIn('교사용 저장 실패',refreshed['conversion']['retry_error'])
        self.assertIn(server.EXPORT_ARCHIVE,refreshed['files'])
        saved=core.save_exam(exam)
        stored=next(item for item in saved['exports'] if item['id']==bundle['id'])
        self.assertEqual(stored['conversion']['status'],'ready')
        self.assertEqual({name:(folder/name).read_bytes() for name in protected},original)

    def test_internal_hml_download_is_blocked_for_unavailable_bundle(self):
        with patch.object(server,'hwp_conversion_available',return_value=False):
            bundle=server.export_exam(self.exam)
        self.store_bundle(bundle)
        request_path=f'/download/{self.exam["id"]}/{bundle["id"]}/시험지_학생용.hml'

        class MemoryHandler(server.Handler):
            def __init__(inner):
                inner.path=request_path;inner.headers={'Host':'127.0.0.1'};inner.wfile=io.BytesIO()
                inner.status=None
            def send_response(inner,status,message=None): inner.status=status
            def send_header(inner,key,value): pass
            def end_headers(inner): pass

        handler=MemoryHandler();handler.do_GET()
        self.assertEqual(handler.status,404)
        self.assertIn('공개된 출력물',handler.wfile.getvalue().decode('utf-8'))

    def legacy_bundle(self):
        bundle=server.export_exam(self.exam,convert_hwpx=False)
        folder=core.exam_path(self.exam['id'])/'exports'/bundle['id']
        (folder/'정답과해설.hml').unlink()
        for name in server.EXPORT_DOCUMENTS[:2]: fake_hwpx(folder/name,folder/Path(name).with_suffix('.hml'))
        bundle['conversion']={'status':'ready','message':'기존 시험지 변환 완료'}
        (folder/'정답과해설.md').write_text('# 이전 시험 — 정답 및 해설\n',encoding='utf-8')
        legacy=[*server.EXPORT_DOCUMENTS[:2],'정답과해설.md',*server.EXPORT_SUPPORT_FILES]
        with zipfile.ZipFile(folder/server.EXPORT_ARCHIVE,'w') as archive:
            for name in legacy: archive.write(folder/name,name)
        bundle['files']=[*legacy,server.EXPORT_ARCHIVE]
        self.store_bundle(bundle)
        return bundle,folder

    def test_legacy_markdown_upgrade_uses_export_snapshot(self):
        bundle,folder=self.legacy_bundle()
        original=self.exam['cards'][0]['explanation']
        self.exam['cards'][0]['explanation']='현재 편집 중인 다른 해설'
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=self.successful_process):
            result=server.recalculate_export(self.exam,bundle['id'])
        self.assertEqual(result['conversion']['status'],'ready')
        text=''.join(ET.parse(folder/'정답과해설.hml').getroot().itertext())
        self.assertIn(original,text)
        self.assertNotIn('현재 편집 중인 다른 해설',text)
        self.assertIn('정답과해설.hwpx',result['files'])
        self.assertNotIn('정답과해설.md',result['files'])
        with zipfile.ZipFile(folder/server.EXPORT_ARCHIVE) as archive:
            self.assertNotIn('정답과해설.md',archive.namelist())

    def test_legacy_upgrade_failure_preserves_existing_files_and_manifest(self):
        bundle,folder=self.legacy_bundle()
        original_files=list(bundle['files'])
        original={name:(folder/name).read_bytes() for name in original_files}
        def fail_answer(command,**kwargs):
            args=command[3:]
            for source,destination in zip(args[:4:2],args[1:4:2]): fake_hwpx(destination,source)
            return SimpleNamespace(returncode=1,stdout='',stderr='정답·해설 저장 실패')
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=fail_answer):
            result=server.recalculate_export(self.exam,bundle['id'])
        self.assertIn('retry_error',result['conversion'])
        self.assertEqual(result['files'],original_files)
        self.assertEqual({name:(folder/name).read_bytes() for name in original_files},original)
        self.assertFalse((folder/'정답과해설.hwpx').exists())

    def test_answer_equations_missing_prevents_publication(self):
        def drop_answer_equations(command,**kwargs):
            args=command[3:]
            for index,(source,destination) in enumerate(zip(args[0::2],args[1::2])):
                fake_hwpx(destination,source,keep_equations=index!=2)
            return SimpleNamespace(returncode=0,stdout='',stderr='')
        self.exam['cards'][0]['explanation']=r'물리량은 $P_0 V_0$이다.'
        self.exam['card_approval']={'digest':core.cards_digest(self.exam['cards'])}
        with patch.object(server,'hwp_conversion_available',return_value=True), \
             patch.object(server.subprocess,'run',side_effect=drop_answer_equations):
            bundle=server.export_exam(self.exam)
        self.assertEqual(bundle['conversion']['status'],'failed')
        self.assertFalse(any(name.endswith('.hwpx') for name in bundle['files']))


if __name__=='__main__': unittest.main(verbosity=2)
