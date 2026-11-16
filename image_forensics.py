"""上传图片的 AI 生成痕迹检测。

两层判断，只做标记不做拦截：
- 强信号：文件里带 C2PA / 内容凭证 / OpenAI 出图标记，命中基本可确认来自 ChatGPT 等生成工具；
- 弱信号：尺寸命中文生图模型的固定出图规格，只能提示管理员留意。

注意：手机截图、转发、二次压缩都会去掉元数据，所以检测不到不代表图片一定真实。
"""
import io

STRONG_MARKERS = (
    b'caBX',            # PNG 里的 C2PA 数据块
    b'jumb',            # JUMBF 容器（C2PA 载体）
    b'jumbf',
    b'c2pa',
    b'C2PA',
    b'c2pa.claim',
    b'trainedAlgorithmicMedia',
    b'digitalSourceType',
    b'OpenAI',
    b'openai',
    b'DALL-E',
    b'DALL\xc2\xb7E',
    b'gpt-image',
    b'ChatGPT',
)
STRONG_REASON = '文件带有 C2PA 内容凭证或 OpenAI 出图标记，基本可确认由 AI 生成'
OPENAI_SIZES = {
    (1024, 1024), (1536, 1024), (1024, 1536),
    (1792, 1024), (1024, 1792),
    (2048, 2048), (1536, 1536),
}
WEAK_REASON = '图片尺寸与 AI 出图规格一致，可能是生成图'
MAX_SCAN = 12 * 1024 * 1024


def inspect_upload(data):
    """返回 (level, reason)：0 未发现异常，1 可疑，2 高度疑似 AI 生成。"""
    if not data:
        return 0, None
    raw = data[:MAX_SCAN]
    for marker in STRONG_MARKERS:
        if marker in raw:
            return 2, STRONG_REASON
    try:
        from PIL import Image
        with Image.open(io.BytesIO(raw)) as image:
            size = image.size
            fmt = (image.format or '').upper()
    except Exception:
        return 0, None
    if size in OPENAI_SIZES:
        detail = '（%d×%d，%s）' % (size[0], size[1], fmt or '未知格式')
        return 1, WEAK_REASON + detail
    return 0, None
