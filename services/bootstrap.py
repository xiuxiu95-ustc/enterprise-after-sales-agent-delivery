from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from config.settings import Settings
from db.models import Engineer, EngineerShift, KnowledgeDocument
from services.memory import text_embedding


def seed_reference_data(db: Session, settings: Settings) -> None:
    if db.query(Engineer.id).first() is None:
        engineers = [
            Engineer(employee_code="E-NET-001", name="张伟", skills=["network", "router", "remote"], service_regions=["北京", "上海"]),
            Engineer(employee_code="E-HW-002", name="李娜", skills=["hardware", "printer", "installation"], service_regions=["北京"]),
            Engineer(employee_code="E-HVAC-003", name="王强", skills=["hvac", "appliance", "maintenance"], service_regions=["北京", "天津"]),
            Engineer(employee_code="E-SW-004", name="陈晨", skills=["software", "system", "remote"], service_regions=[]),
        ]
        for engineer in engineers:
            engineer.skill_embedding = text_embedding(" ".join(engineer.skills))
            db.add(engineer)
        db.flush()
        start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=366)
        for engineer in engineers:
            db.add(EngineerShift(engineer_id=engineer.id, start_time=start, end_time=end, status="available"))
    if db.query(KnowledgeDocument.id).first() is None:
        docs = [
            KnowledgeDocument(
                collection=settings.rag_collection,
                title="企业售后服务分级与 SLA",
                content="P1 全面中断 15 分钟响应；P2 核心功能受损 2 小时响应；P3 一般咨询 1 个工作日响应。",
                source_uri="kb://after-sales/sla",
                keywords=["SLA", "响应时间", "故障等级"],
            ),
            KnowledgeDocument(
                collection=settings.rag_collection,
                title="保修与上门服务规则",
                content="保修期内的非人为硬件故障免基础检测费。上门前需确认产品型号、序列号、地址和联系人。",
                source_uri="kb://after-sales/warranty",
                keywords=["保修", "上门", "费用"],
            ),
            KnowledgeDocument(
                collection=settings.rag_collection,
                title="预约变更与取消",
                content="预约开始前 2 小时可自助取消；变更预约使用原工单版本号，冲突时需刷新后重试。",
                source_uri="kb://appointment/change-policy",
                keywords=["预约", "取消", "版本号", "冲突"],
            ),
        ]
        db.add_all(docs)
    db.commit()

