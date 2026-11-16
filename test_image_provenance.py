import io,unittest,struct,zlib
from PIL import Image
from PIL.PngImagePlugin import PngInfo
import image_forensics
class ProvenanceTests(unittest.TestCase):
    def image(self,**metadata):
        data=io.BytesIO();info=PngInfo()
        for key,value in metadata.items():info.add_text(key,value)
        Image.new('RGB',(1024,1024)).save(data,'PNG',pnginfo=info)
        return data.getvalue()
    def test_dimensions_and_brand_mentions_are_not_generation_evidence(self):
        self.assertEqual(image_forensics.inspect_upload(self.image())[0],0)
        self.assertEqual(image_forensics.inspect_upload(self.image(Comment='讨论 OpenAI 和 ChatGPT 的截图'))[0],0)
    def test_cabx_chunk_detected_even_when_pillow_omits_it(self):
        data=self.image(); payload=b'example provenance payload'; tag=b'caBX'
        chunk=struct.pack('>I',len(payload))+tag+payload+struct.pack('>I',zlib.crc32(tag+payload))
        level,reason=image_forensics.inspect_upload(data[:33]+chunk+data[33:])
        self.assertEqual(level,1);self.assertIn('不能',reason)

    def test_provenance_is_only_a_neutral_hint(self):
        level,reason=image_forensics.inspect_upload(self.image(c2pa='manifest'))
        self.assertEqual(level,1)
        self.assertNotIn('基本可确认',reason)
        self.assertIn('不能',reason)

import test_app as base
m=base.m
class UpgradeTests(unittest.TestCase):
    setUp=base.Flow.setUp
    def test_old_heuristic_flags_are_cleared_without_changing_review_status(self):
        reasons=['图片尺寸与 AI 出图规格一致，可能是生成图（1024×1024，PNG）','文件带有 C2PA 内容凭证或 OpenAI 出图标记，基本可确认由 AI 生成',image_forensics.inspect_upload(ProvenanceTests().image(c2pa='manifest'))[1]]
        with m.db() as c:
            uid=c.execute("SELECT id FROM users WHERE name='coach'").fetchone()[0]
            for level,reason in zip((1,2,1),reasons):
                c.execute("INSERT INTO records(user_id,sport,minutes,effort,note,image,created,status,suspect,suspect_reason) VALUES(?,'跑步',30,5,'','x.jpg',?,'approved',?,?)",(uid,m.now(),level,reason))
        m.init();m.init()
        with m.db() as c:
            rows=c.execute('SELECT status,suspect,suspect_reason FROM records ORDER BY id').fetchall()
            self.assertEqual([(r['status'],r['suspect']) for r in rows],[('approved',0),('approved',0),('approved',1)])
            self.assertIsNone(rows[0]['suspect_reason']);self.assertIsNone(rows[1]['suspect_reason'])
