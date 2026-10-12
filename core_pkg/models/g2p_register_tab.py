import re
import uuid

from sqlalchemy import Boolean, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from openg2p_fastapi_common.models import BaseORMModel


class G2PRegisterUITab(BaseORMModel):
    __tablename__ = "g2p_register_ui_tabs"

    tab_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    register_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tab_label: Mapped[str] = mapped_column(String, nullable=False)
    tab_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # server_default so a fresh create_all gives the NOT NULL columns a DDL
    # default — raw-SQL seed inserts that omit them (and existing rows after the
    # ALTER migration) then get a value without the Python-side default.
    used_for_new_intake_form: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    no_of_verifications_required: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    intake_form_name: Mapped[str] = mapped_column(String, nullable=True)
    intake_form_description: Mapped[str] = mapped_column(String, nullable=True)
    intake_form_auto_approve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))

    @validates("tab_label")
    def validate_tab_label(self, _key: str, tab_label_value: str) -> str:
        if tab_label_value:
            pattern: str = r"^[a-z][a-z0-9_]*$"
            if not re.match(pattern, tab_label_value):
                raise ValueError(
                    f"tab_label must be lowercase with underscores only. "
                    f"Got: '{tab_label_value}'. Example valid: 'personal_info'"
                )
        return tab_label_value


class G2PRegisterUITabSection(BaseORMModel):
    __tablename__ = "g2p_register_ui_tab_sections"

    tab_section_id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # TODO: check usage and remove register_id
    register_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tab_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    section_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    section_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
