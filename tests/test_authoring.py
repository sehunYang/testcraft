"""Authoring invariants, using temporary projects and deterministic CLI results."""
import copy
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import openpyxl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.runtime/packages'))
from app import core, server, cli, images, catalog
from test_support import cleanup_tempdir
from test_workflow import card

class AuthoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=core.ROOT/'.runtime')
        self.patch=patch.object(core,'DATA',Path(self.tmp.name)/'studio');self.patch.start()
    def tearDown(self):
        self.patch.stop();cleanup_tempdir(self.tmp)
    def exam(self,cards):
        return core.save_exam({'id':core.uid(),'title':'테스트','subject':'12역학','cards':cards,'exports':[],'revision':0})
    def result(self):
        c=card();c.update(estimate=.5,discrimination=.3)
        return {k:c[k] for k in cli.QUESTION_SCHEMA['properties']}
    def wait_job(self,job):
        deadline=time.monotonic()+10
        while job['exam_id'] in server.ACTIVE and time.monotonic()<deadline: time.sleep(.02)
        self.assertNotIn(job['exam_id'],server.ACTIVE)
    def test_subject_boundaries(self):
        core.check_subject('12역학',[card()])
        with self.assertRaises(ValueError):core.check_subject('12물리',[card()])
        self.assertEqual(catalog.subject_id('[10통과1-01-01]'),'10통과1')
        self.assertEqual(catalog.subject_id('[10통과2-01-01]'),'10통과2')
        self.assertEqual(catalog.infer_subject([card()]),'12역학')
        self.assertTrue(all(catalog.subject_id(code) for code in core.standards()))
    def test_bulk_only_yes_partial_failure_and_retry(self):
        cards=[card(no=n) for n in (1,2,3)]
        cards[0]['ai_requested']=False
        exam=self.exam(cards)
        with patch.object(cli,'discover',return_value='mock-cli'),patch.object(cli,'execute',side_effect=[ValueError('검증용 실패'),self.result()]) as execute:
            job=server.launch_job(exam['id'],{'action':'question'})
            self.wait_job(job)
            self.assertEqual(execute.call_count,2)
        saved=core.read_exam(exam['id'])
        self.assertEqual(job['status'],'partial')
        self.assertEqual([c['ai_requested'] for c in saved['cards']],[False,True,False])
        self.assertEqual(saved['cards'][0],cards[0])
        self.assertEqual(saved['cards'][1],cards[1])
        with patch.object(cli,'discover',return_value='mock-cli'),patch.object(cli,'execute',return_value=self.result()) as execute:
            retry=server.launch_job(exam['id'],{'action':'question'});self.wait_job(retry)
            self.assertEqual(execute.call_count,1)
        self.assertFalse(any(c['ai_requested'] for c in core.read_exam(exam['id'])['cards']))
    def test_cancel_keeps_unfinished_yes(self):
        exam=self.exam([card(no=1),card(no=2)])
        def cancel(*args): args[-1].set();return self.result()
        with patch.object(cli,'discover',return_value='mock-cli'),patch.object(cli,'execute',side_effect=cancel):
            job=server.launch_job(exam['id'],{'action':'question'});self.wait_job(job)
        self.assertEqual(job['status'],'cancelled')
        self.assertTrue(all(c['ai_requested'] for c in core.read_exam(exam['id'])['cards']))
    def test_image_plan_modes_and_invalidation(self):
        c=card();c.update(data_kind='image',image_mode='strict',image_locked='물체 두 개, 길이 1:2, 라벨 A/B',image_creative='배경')
        self.assertTrue(core.image_plan_errors(c))
        self.assertIn('글씨 없음', ' '.join(core.image_plan_errors(c)))
        c.update(image_creative='',image_text_none=True);self.assertFalse(core.image_plan_errors(c))
        self.assertFalse(core.image_plan_confirmed(c))
        c['image_plan_approval']={'context':core.image_plan_context(c)}
        self.assertTrue(core.image_plan_confirmed(c))
        c['image_locked']='길이 1:3';self.assertFalse(core.image_plan_confirmed(c))
        with self.assertRaises(ValueError):server.select_job_cards({'cards':[c]},{'action':'image'})
    def test_teacher_mode_is_preserved(self):
        c=card();c['image_mode']='strict';result=self.result();result.update(data_kind='image',image_mode='mixed',image_locked='도형',image_creative='외형')
        with self.assertRaisesRegex(ValueError,'변경'):server.apply_question_result(c,result)
    def test_authoring_metadata_is_independent_of_approval_and_digest(self):
        c=card();exam=self.exam([c])
        exam['card_approval']={'digest':core.cards_digest(exam['cards']),'approved_at':core.now()}
        core.save_exam(exam)
        saved=core.read_exam(exam['id']);before_export=core.export_digest(saved)
        saved['cards'][0].update(authoring_mode='manual',materials_request='그림 두 장과 표',material_request_kinds=['image','table'],material_request_image_mode='mixed',ai_requested=False)
        core.save_exam(saved)
        loaded=core.read_exam(exam['id'])
        self.assertEqual(loaded['cards'][0]['authoring_mode'],'manual')
        self.assertEqual(loaded['cards'][0]['materials_request'],'그림 두 장과 표')
        self.assertEqual(loaded['cards'][0]['material_request_kinds'],['image','table'])
        self.assertEqual(loaded['cards'][0]['material_request_image_mode'],'mixed')
        self.assertTrue(loaded['cards'][0]['review_approved'])
        self.assertTrue(core.cards_approved(loaded))
        self.assertEqual(core.export_digest(loaded),before_export)
    def test_missing_mode_stays_legacy_even_when_request_is_no(self):
        c=card();c.pop('authoring_mode');c.pop('materials_request');c['ai_requested']=False
        normalized=core.normalize(c,1)
        self.assertEqual(normalized['authoring_mode'],'legacy')
        self.assertEqual(normalized['materials_request'],'')
    def test_mode_changes_and_older_clients_keep_one_run_flag_and_metadata(self):
        previous=card();previous.update(authoring_mode='ai',materials_request='두 그림',material_request_kinds=['image','table'],material_request_image_mode='mixed',ai_requested=False)
        old_client_raw=copy.deepcopy(previous)
        for key in ('authoring_mode','materials_request','material_request_kinds','material_request_image_mode','ai_requested'):old_client_raw.pop(key)
        normalized=core.normalize(old_client_raw,1)
        server.preserve_authoring_metadata(normalized,old_client_raw,previous)
        self.assertEqual((normalized['authoring_mode'],normalized['materials_request'],normalized['material_request_kinds'],normalized['material_request_image_mode'],normalized['ai_requested']),('ai','두 그림',['image','table'],'mixed',False))
        changed=copy.deepcopy(previous);changed['authoring_mode']='manual'
        server.preserve_authoring_metadata(changed,{'authoring_mode':'manual'},previous)
        self.assertFalse(changed['ai_requested'])
        new_manual=core.normalize({'id':core.uid(),'authoring_mode':'manual'},1)
        server.preserve_authoring_metadata(new_manual,{'id':new_manual['id'],'authoring_mode':'manual'},None)
        self.assertFalse(new_manual['ai_requested'])
    def test_invalid_mode_and_long_materials_request_are_rejected(self):
        c=card();c['authoring_mode']='automatic'
        with self.assertRaisesRegex(ValueError,'작성 방식'):core.normalize(c,1)
        c=card();c['materials_request']='x'*(core.MATERIALS_REQUEST_MAX+1)
        with self.assertRaisesRegex(ValueError,'자 이하여야'):core.normalize(c,1)

    def test_material_request_preferences_default_trim_validate_and_keep_digests(self):
        c=card()
        self.assertEqual(c['material_request_kinds'],[])
        self.assertEqual(c['material_request_image_mode'],'')
        c.update(material_request_kinds=[' image ','table','image'],material_request_image_mode=' strict ')
        normalized=core.normalize(c,1)
        self.assertEqual(normalized['material_request_kinds'],['image','table'])
        self.assertEqual(normalized['material_request_image_mode'],'strict')
        self.assertNotIn('material_request_kinds',cli.QUESTION_SCHEMA['properties'])
        self.assertNotIn('material_request_image_mode',cli.QUESTION_SCHEMA['properties'])
        exam=self.exam([normalized]);before_hash=core.content_hash(normalized);before_cards=core.cards_digest([normalized]);before_export=core.export_digest(exam)
        normalized['material_request_kinds']=['text'];normalized['material_request_image_mode']='flexible'
        self.assertEqual(core.content_hash(normalized),before_hash)
        self.assertEqual(core.cards_digest([normalized]),before_cards)
        exam['cards']=[normalized]
        self.assertEqual(core.export_digest(exam),before_export)
        for value in ('image','other', ['image',None]):
            bad=card();bad['material_request_kinds']=value
            with self.assertRaises(ValueError):core.normalize(bad,1)
        bad=card();bad['material_request_kinds']=['table'];bad['material_request_image_mode']='strict'
        with self.assertRaisesRegex(ValueError,'image를 포함'):core.normalize(bad,1)
        bad=card();bad['material_request_kinds']=['image'];bad['material_request_image_mode']='other'
        with self.assertRaisesRegex(ValueError,'strict / mixed / flexible'):core.normalize(bad,1)
        ai_choice=card();ai_choice['material_request_image_mode']='mixed'
        self.assertEqual(core.normalize(ai_choice,1)['material_request_image_mode'],'mixed')
    def test_manual_cards_need_an_explicit_one_shot_ai_request(self):
        c=card();c.update(authoring_mode='manual',ai_requested=True);exam={'cards':[c]}
        with self.assertRaises(ValueError):server.select_job_cards(exam,{'action':'question'})
        self.assertEqual(server.select_job_cards(exam,{'action':'question','card_id':c['id']}),[c])
        c['ai_requested']=False
        with self.assertRaises(ValueError):server.select_job_cards(exam,{'action':'question','card_id':c['id']})
    def test_materials_request_is_in_question_prompt(self):
        c=card();c['authoring_mode']='ai';c['materials_request']='두 장의 그림 (가), (나)와 자료 표를 만들어 주세요.'
        prompt=cli.prompt_for(c,'question',subject='역학과 에너지')
        self.assertIn(c['materials_request'],prompt)
        self.assertIn('ID·종류·순서·이름표·그림 유형',prompt)

    def test_material_request_preferences_are_in_question_prompt(self):
        c=card();c.update(material_request_kinds=['image','text','table'],material_request_image_mode='strict')
        prompt=cli.prompt_for(c,'question')
        self.assertIn('그림(image), 글상자(text), 표(table)',prompt)
        self.assertIn('최소 하나씩',prompt)
        self.assertIn('새 자료 블록은 선택한 종류로만 추가',prompt)
        self.assertIn('strict 유형을 적용',prompt)
        self.assertIn('기존 그림에 이미 지정된 그림 유형은 그대로 보존',prompt)
    def test_question_result_keeps_mode_request_and_existing_materials(self):
        c=card();c.update(authoring_mode='manual',materials_request='기존 그림 뒤에 표를 추가',ai_requested=True)
        image_id='a'*16
        saved_image={'file':'original.svg','svg':'<svg/>','approved':False}
        c['materials']=[{'id':image_id,'kind':'image','label':'(가)','content':'원래 그림 설명',
                         'image_mode':'strict','image_locked':'수평 바닥선','image_creative':'',
                         'image_text_none':True,'image_plan_version':2,'image':saved_image,
                         'image_labels':[],'labels_initialized':False,'image_scene':None,'image_plan_approval':None}]
        result=self.result();result['materials']=[
            {'id':image_id,'kind':'image','label':'(가)','content':'원래 그림 설명',
             'image_mode':'strict','image_locked':'수평 바닥선','image_creative':'',
             'image_text_none':True,'image_plan_version':2},
            {'id':'','kind':'table','label':'자료 표','content':'| t | v |\n|---|---|\n| 0 | 0 |'}]
        result['authoring_mode']='ai';result['materials_request']='모델 출력으로 덮지 말 것'
        updated=server.apply_question_result(c,result)
        self.assertEqual(updated['authoring_mode'],'manual')
        self.assertEqual(updated['materials_request'],'기존 그림 뒤에 표를 추가')
        self.assertFalse(updated['ai_requested'])
        blocks=core.material_blocks(updated)
        self.assertEqual([b['id'] for b in blocks[:1]],[image_id])
        self.assertEqual([b['kind'] for b in blocks],['image','table'])
        self.assertEqual(blocks[0]['image_mode'],'strict')
        self.assertEqual(blocks[0]['image'],saved_image)
    def test_manual_image_can_receive_unset_mode_but_cannot_change_selected_mode(self):
        image_id='a'*16;table_id='b'*16
        saved_image={'file':'kept.svg','svg':'<svg/>','approved':False}
        c=card();c.update(authoring_mode='manual',materials_request='기존 자료 유지',ai_requested=True,
                          materials=[{'id':image_id,'kind':'image','label':'(가)','content':'그림 설명',
                                      'image_mode':'','image_locked':'','image_creative':'',
                                      'image_text_none':True,'image_plan_version':2,'image':copy.deepcopy(saved_image),
                                      'image_labels':[],'labels_initialized':False,'image_scene':None,'image_plan_approval':None},
                                     {'id':table_id,'kind':'table','label':'자료 표','content':'| t | v |\n|---|---|\n| 0 | 0 |'}])
        result=self.result();result['materials']=[
            {'id':image_id,'kind':'image','label':'(가)','content':'그림 설명',
             'image_mode':'strict','image_locked':'수평 바닥선','image_creative':'',
             'image_text_none':True,'image_plan_version':2},
            {'id':table_id,'kind':'table','label':'자료 표','content':'| t | v |\n|---|---|\n| 0 | 0 |'}]
        updated=server.apply_question_result(c,result)
        blocks=core.material_blocks(updated)
        self.assertEqual([b['id'] for b in blocks],[image_id,table_id])
        self.assertEqual([b['kind'] for b in blocks],['image','table'])
        self.assertEqual(blocks[0]['image_mode'],'strict')
        self.assertEqual(blocks[0]['image'],saved_image)
        self.assertEqual(updated['authoring_mode'],'manual')
        self.assertEqual(updated['materials_request'],'기존 자료 유지')

        selected=copy.deepcopy(c);selected['materials'][0]['image_mode']='strict'
        changed=copy.deepcopy(result)
        changed['materials'][0].update(image_mode='mixed',image_locked='floor: 바닥',image_creative='ball: 공')
        with self.assertRaisesRegex(ValueError,'변경'):
            server.apply_question_result(selected,changed)

    def test_selected_material_kinds_and_image_mode_apply_to_new_and_unset_existing_materials(self):
        image_id='a'*16
        saved_image={'file':'kept.svg','svg':'<svg/>','approved':False}
        c=card();c.update(authoring_mode='manual',materials_request='그림 뒤에 표',material_request_kinds=['image','table'],material_request_image_mode='strict',ai_requested=True,
                          materials=[{'id':image_id,'kind':'image','label':'(가)','content':'그림 설명',
                                      'image_mode':'','image_locked':'','image_creative':'',
                                      'image_text_none':True,'image_plan_version':2,'image':copy.deepcopy(saved_image),
                                      'image_labels':[],'labels_initialized':False,'image_scene':None,'image_plan_approval':None}])
        result=self.result();result['materials']=[
            {'id':image_id,'kind':'image','label':'(가)','content':'그림 설명',
             'image_mode':'','image_locked':'floor: 수평 바닥선','image_creative':'',
             'image_text_none':True,'image_plan_version':2},
            {'id':'','kind':'table','label':'자료 표','content':'| t | v |\n|---|---|\n| 0 | 0 |'}]
        result['material_request_kinds']=['text'];result['material_request_image_mode']='mixed'
        updated=server.apply_question_result(c,result)
        blocks=core.material_blocks(updated)
        self.assertEqual(blocks[0]['id'],image_id)
        self.assertNotEqual(blocks[1]['id'],image_id)
        self.assertEqual([b['kind'] for b in blocks],['image','table'])
        self.assertEqual(blocks[0]['image_mode'],'strict')
        self.assertEqual(blocks[0]['image'],saved_image)
        self.assertEqual(updated['material_request_kinds'],['image','table'])
        self.assertEqual(updated['material_request_image_mode'],'strict')

    def test_existing_teacher_image_mode_wins_and_new_image_mismatch_is_rejected(self):
        image_id='a'*16
        existing=card();existing.update(material_request_kinds=['image'],material_request_image_mode='strict',
            materials=[{'id':image_id,'kind':'image','label':'(가)','content':'그림',
                        'image_mode':'mixed','image_locked':'floor: 바닥','image_creative':'ball: 공',
                        'image_text_none':True,'image_plan_version':2}])
        result=self.result();result['materials']=[
            {'id':image_id,'kind':'image','label':'(가)','content':'그림',
             'image_mode':'mixed','image_locked':'floor: 바닥','image_creative':'ball: 공',
             'image_text_none':True,'image_plan_version':2}]
        updated=server.apply_question_result(existing,result)
        self.assertEqual(core.material_blocks(updated)[0]['image_mode'],'mixed')

        fresh=card();fresh.update(material_request_kinds=['image'],material_request_image_mode='strict')
        wrong=self.result();wrong['materials']=[
            {'id':'','kind':'image','label':'','content':'그림',
             'image_mode':'mixed','image_locked':'floor: 바닥','image_creative':'ball: 공',
             'image_text_none':True,'image_plan_version':2}]
        with self.assertRaisesRegex(ValueError,'요청한 새 그림 유형'):
            server.apply_question_result(fresh,wrong)

    def test_selected_image_mode_fills_a_new_image_when_model_leaves_it_blank(self):
        c=card();c.update(material_request_kinds=['image'],material_request_image_mode='strict')
        result=self.result();result['materials']=[
            {'id':'','kind':'image','label':'','content':'그림 설명',
             'image_mode':'','image_locked':'floor: 수평 바닥선','image_creative':'',
             'image_text_none':True,'image_plan_version':2}]
        updated=server.apply_question_result(c,result)
        self.assertEqual(core.material_blocks(updated)[0]['image_mode'],'strict')

    def test_requested_kind_must_be_present_but_empty_kind_selection_stays_free(self):
        c=card();c['material_request_kinds']=['table']
        result=self.result();result['materials']=[]
        with self.assertRaisesRegex(ValueError,'요청한 자료 종류가 없습니다'):
            server.apply_question_result(c,result)

        free=card();free['material_request_kinds']=[]
        result=self.result();result['materials']=[{'id':'','kind':'text','label':'','content':'(글상자) 설명'}]
        self.assertEqual(core.material_blocks(server.apply_question_result(free,result))[0]['kind'],'text')

    def test_selected_kinds_limit_new_blocks_and_keep_existing_unselected_kinds(self):
        image_id='a'*16;saved_image={'file':'kept.svg','svg':'<svg/>','approved':False}
        c=card();c.update(material_request_kinds=['table'],materials=[
            {'id':image_id,'kind':'image','label':'(가)','content':'기존 그림',
             'image_mode':'mixed','image_locked':'floor: 바닥','image_creative':'ball: 공',
             'image_text_none':True,'image_plan_version':2,'image':copy.deepcopy(saved_image)}])
        result=self.result();result['materials']=[
            {'id':image_id,'kind':'image','label':'(가)','content':'기존 그림',
             'image_mode':'mixed','image_locked':'floor: 바닥','image_creative':'ball: 공',
             'image_text_none':True,'image_plan_version':2},
            {'id':'','kind':'table','label':'표','content':'| t | v |\n|---|---|\n| 0 | 0 |'}]
        updated=server.apply_question_result(c,result)
        blocks=core.material_blocks(updated)
        self.assertEqual([block['kind'] for block in blocks],['image','table'])
        self.assertEqual(blocks[0]['id'],image_id)
        self.assertEqual(blocks[0]['image'],saved_image)

        fresh=card();fresh['material_request_kinds']=['table']
        wrong=self.result();wrong['materials']=[{'id':'','kind':'image','label':'','content':'그림'}]
        with self.assertRaisesRegex(ValueError,'선택하지 않은 자료 종류'):
            server.apply_question_result(fresh,wrong)
    def test_layers_and_prompt(self):
        svg='<svg viewBox="0 0 1000 640"><g id="geometry"/><g id="labels"/></svg>'
        images.validate_mode_layers(svg,'strict')
        with self.assertRaises(ValueError):images.validate_mode_layers(svg,'mixed')
        images.validate_mode_layers(svg.replace('</svg>','<g id="illustration"/></svg>'),'mixed')
        for kind in ('question','image'):
            prompt=cli.prompt_for(card(),kind,subject='역학과 에너지')
            for word in ('strict:','mixed:','flexible:','image_locked','image_creative'):self.assertIn(word,prompt)
    def test_flags_do_not_revoke_approval(self):
        c=card();digest=core.cards_digest([c]);c['ai_requested']=False;c['ai_feedback']='문두 수정'
        self.assertEqual(digest,core.cards_digest([c]))
    def test_xlsx_retains_authoring_metadata(self):
        c=card();c.update(ai_requested=True,authoring_mode='ai',materials_request='(가)와 (나) 두 그림',material_request_kinds=['image','table'],material_request_image_mode='mixed',image_mode='mixed',image_locked='수평선, 객체 두 개',image_creative='상자 외관',ai_feedback='보기 개선',image_text_none=True)
        target=Path(self.tmp.name)/'cards.xlsx';core.export_xlsx([c],target)
        read=core.import_cards(target.read_bytes())[0]
        for key in ('ai_requested','authoring_mode','materials_request','material_request_kinds','material_request_image_mode','image_mode','image_locked','image_creative','ai_feedback','image_text_none'):self.assertEqual(read[key],c[key])

    def test_xlsx_rejects_invalid_material_request_metadata_clearly(self):
        c=card();target=Path(self.tmp.name)/'cards.xlsx';core.export_xlsx([c],target)
        wb=openpyxl.load_workbook(target);sheet=wb['문항카드 생성'];sheet['AK11']='not-json';wb.save(target)
        with self.assertRaisesRegex(ValueError,'필요한 자료 종류 JSON을 확인'):
            core.import_cards(target.read_bytes())

        core.export_xlsx([c],target)
        wb=openpyxl.load_workbook(target);sheet=wb['문항카드 생성'];sheet['AK11']='["image"]';sheet['AL11']='not-a-mode';wb.save(target)
        with self.assertRaisesRegex(ValueError,'요청 그림 유형은 strict / mixed / flexible'):
            core.import_cards(target.read_bytes())
    def test_delete_is_recoverable_and_active_blocked(self):
        e=self.exam([card()]);server.ACTIVE[e['id']]='busy'
        try:
            with self.assertRaises(ValueError):server.delete_exam(e['id'],e['title'])
        finally:server.ACTIVE.pop(e['id'])
        with self.assertRaises(ValueError):server.delete_exam(e['id'],'다른 제목')
        server.delete_exam(e['id'],e['title'])
        self.assertFalse(core.exam_path(e['id']).exists())
        self.assertTrue((core.DATA.parent/'_studio_trash'/e['id']/'project.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
