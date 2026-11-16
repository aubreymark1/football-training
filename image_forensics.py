"""读取图片来源信息，仅提示人工核对，不判定是否为 AI 生成。

普通尺寸、品牌文字和内容凭证均不能证明训练截图造假。
来源信息也可能被移除或自行填写，审核仍需核对训练内容。
"""
import io,struct

def has_provenance_container(data):
    # PNG Content Credentials are stored in caBX chunks, which Pillow does not
    # generally include in image.info. Inspect chunk boundaries, not raw text.
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        offset=8
        while offset+12<=len(data):
            size=struct.unpack_from('>I',data,offset)[0]; end=offset+12+size
            if end>len(data): return False
            if data[offset+4:offset+8]==b'caBX': return True
            offset=end
        return False
    # JPEG JUMBF uses APP11 segments. The signal is only an unverified hint.
    if data.startswith(b'\xff\xd8'):
        offset=2
        while offset+4<=len(data) and data[offset]==255:
            marker=data[offset+1];offset+=2
            if marker in (0xda,0xd9): break
            if marker in (0x01,0xd8) or 0xd0<=marker<=0xd7: continue
            if offset+2>len(data): break
            size=int.from_bytes(data[offset:offset+2],'big')
            if size<2 or offset+size>len(data): break
            payload=data[offset+2:offset+size]
            if marker==0xeb and payload.startswith(b'JP') and (b'jumb' in payload or b'c2pa' in payload.lower()): return True
            offset+=size
    return False

def inspect_upload(data):
    """返回 (0 无来源提示 / 1 有来源信息, 说明)。"""
    if not data:return 0,None
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            metadata=' '.join(str(key)+' '+str(value) for key,value in image.info.items()).lower()
    except Exception:
        return 0,None
    if has_provenance_container(data) or any(marker in metadata for marker in ('c2pa','jumbf','trainedalgorithmicmedia','digitalsourcetype')):
        return 1,'图片含来源信息，仅凭这些信息不能判断是否为 AI 生成，请结合训练内容核对。'
    return 0,None
