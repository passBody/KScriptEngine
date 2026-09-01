# -*- coding: utf-8 -*-
"""
合成卡片定义（body + 签名 的纯数据捆绑）
======================================

:class:`CompositeDefinition` 把一张合成卡片的**定义体**（:class:`StepList`）
与其**参数签名**（:class:`CompositeSignature`）捆在一起，供
:class:`CompositeCardStore` 存取与 :class:`CompositeCard` 运行期解析。

本模块属 model 层：顶层不导入 PyQt5。
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from model.合成卡片.composite_signature import CompositeSignature

if TYPE_CHECKING:
    from model.步骤.step_list import StepList

__all__ = ["CompositeDefinition"]


@dataclass
class CompositeDefinition:
    """一张合成卡片的定义：体内步骤列表 + 参数签名。"""
    body: "StepList"
    signature: CompositeSignature = field(default_factory=CompositeSignature.empty)


# ================================================================
# 冒烟演示：直接 ``python -m model.合成卡片.composite_definition`` 运行
# ================================================================
if __name__ == "__main__":
    from model.步骤.step_list import StepList
    from model.合成卡片.composite_signature import Param

    body = StepList.create_empty()
    d = CompositeDefinition(body, CompositeSignature(inputs=[Param("x", "number")]))
    assert d.body is body
    assert d.signature.input_names() == ["x"]
    # 签名默认空
    d2 = CompositeDefinition(StepList.create_empty())
    assert d2.signature.is_empty()
    print("CompositeDefinition smoke OK")
