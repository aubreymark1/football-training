"""读取图片来源信息，仅提示人工核对，不判定是否为 AI 生成。

普通尺寸、品牌文字和内容凭证均不能证明训练截图造假。
来源信息也可能被移除或自行填写，审核仍需核对训练内容。
"""
import io

def inspect_upload(data):
    """返回 (0 无来源提示 / 1 有来源信息, 说明)。"""
    if not data:return 0,None
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            metadata=' '.join(str(key)+' '+str(value) for key,value in image.info.items()).lower()
    except Exception:
        return 0,None
    if any(marker in metadata for marker in ('c2pa','jumbf','trainedalgorithmicmedia','digitalsourcetype')):
        return 1,'图片含来源信息，仅凭这些信息不能判断是否为 AI 生成，请结合训练内容核对。'
    return 0,None
