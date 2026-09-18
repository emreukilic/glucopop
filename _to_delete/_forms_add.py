

class PersonDialog(QDialog):
    """Add or edit one followed person: a name, a service, and that service's credentials.

    Deliberately not the full wizard — language, thresholds and appearance are shared by
    everyone, so asking about them again for the second person would be asking twice.
    """

    def __init__(self, cfg, person: dict | None = None, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        from ..config import new_person
        self._person = dict(person) if person else new_person()
        self.setWindowTitle(tr("person_edit") if person else tr("person_add"))
        self.setMinimumSize(560, 520)

        self.name = QLineEdit(self._person.get("name", ""))
        self.name.setPlaceholderText(tr("f_name_auto"))
        self.alerts = QCheckBox(tr("person_alerts"))
        self.alerts.setChecked(bool(self._person.get("alerts", True)))
        self.alerts.setToolTip(tr("person_alerts_help"))

        self.source = QComboBox()
        for sid in sources.SOURCE_INFO:
            self.source.addItem(sources.SOURCES[sid].name, sid)
        start = self._person.get("source") or self.source.itemData(0)
        self.source.setCurrentIndex(max(0, self.source.findData(start)))
        self.source.currentIndexChanged.connect(self._source_changed)

        self.cred = CredentialForm(unit_getter=lambda: cfg["unit"])
        self.cred.tested.connect(lambda *_: self._refresh())
        self.cred.set_source(start, self._person.get("cfg") or {})

        self.hint = QLabel(tr("wz_privacy"))
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet("color: palette(mid); font-size: 11px;")

        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.bb.accepted.connect(self.accept)
        self.bb.rejected.connect(self.reject)

        top = QFormLayout()
        top.addRow(tr("f_name"), self.name)
        top.addRow(tr("s_sensor"), self.source)
        sc = QScrollArea(); sc.setWidgetResizable(True); sc.setFrameShape(QScrollArea.Shape.NoFrame); sc.setWidget(self.cred)
        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(self.alerts)
        lay.addWidget(sc, 1)
        lay.addWidget(self.hint)
        lay.addWidget(self.bb)
        self._refresh()

    def _source_changed(self) -> None:
        sid = self.source.currentData()
        prev = self._person.get("cfg") if self._person.get("source") == sid else {}
        self.cred.set_source(sid, prev or {})
        self._refresh()

    def _refresh(self) -> None:
        # The connection has to be proven before the person can be saved: a person that cannot
        # sign in would sit in the widget showing "--" with no hint as to why.
        ok = self.cred.ok
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok)
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setToolTip("" if ok else tr("wz_need_test"))

    def person(self) -> dict:
        self._person.update(name=self.name.text().strip(), source=self.source.currentData(),
                            cfg=self.cred.values(), alerts=self.alerts.isChecked())
        return self._person


class PeopleBox(QGroupBox):
    """The list of followed people inside the settings dialog: add, edit, remove, reorder-free."""

    def __init__(self, cfg, parent=None):
        super().__init__(tr("people"), parent)
        self.cfg = cfg
        self._people = [dict(p) for p in cfg.people]     # edited copy; applied on OK
        self._removed: list[str] = []

        self.list = QListWidget()
        self.list.setMaximumHeight(132)
        self.list.itemDoubleClicked.connect(lambda *_: self.edit())

        self.add_btn = QPushButton(tr("person_add"))
        self.edit_btn = QPushButton(tr("person_edit"))
        self.del_btn = QPushButton(tr("person_delete"))
        self.add_btn.clicked.connect(self.add)
        self.edit_btn.clicked.connect(self.edit)
        self.del_btn.clicked.connect(self.remove)

        btns = QHBoxLayout()
        btns.addWidget(self.add_btn); btns.addWidget(self.edit_btn); btns.addWidget(self.del_btn); btns.addStretch(1)
        self.help = QLabel(tr("s_people_help"))
        self.help.setWordWrap(True)
        self.help.setStyleSheet("color: palette(mid); font-size: 11px;")
        lay = QVBoxLayout(self)
        lay.addWidget(self.list)
        lay.addLayout(btns)
        lay.addWidget(self.help)
        self._reload()

    def _label(self, p: dict) -> str:
        name = p.get("name") or tr("f_name_auto")
        src = sources.SOURCES[p["source"]].name if p.get("source") in sources.SOURCES else "…"
        return f"{name}   ·   {src}" + ("" if p.get("alerts", True) else f"   ·   {tr('off')}")

    def _reload(self) -> None:
        self.list.clear()
        for p in self._people:
            self.list.addItem(self._label(p))
        self.edit_btn.setEnabled(bool(self._people))
        self.del_btn.setEnabled(len(self._people) > 1)
        from ..config import MAX_PEOPLE
        self.add_btn.setEnabled(len(self._people) < MAX_PEOPLE)

    def _selected(self) -> int:
        return self.list.currentRow() if self.list.currentRow() >= 0 else (0 if self._people else -1)

    def add(self) -> None:
        dlg = PersonDialog(self.cfg, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._people.append(dlg.person())
            self._reload()

    def edit(self) -> None:
        i = self._selected()
        if i < 0:
            return
        dlg = PersonDialog(self.cfg, self._people[i], parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._people[i] = dlg.person()
            self._reload()

    def remove(self) -> None:
        i = self._selected()
        if i < 0 or len(self._people) <= 1:
            return
        p = self._people[i]
        name = p.get("name") or (sources.SOURCES[p["source"]].name if p.get("source") in sources.SOURCES else "…")
        if QMessageBox.question(self, "GlucoPop", tr("person_delete_confirm", name=name)) != QMessageBox.StandardButton.Yes:
            return
        self._removed.append(p["id"])
        self._people.pop(i)
        self._reload()

    def apply(self) -> None:
        """Only touches the config when OK was pressed, so Cancel really cancels."""
        for pid in self._removed:
            self.cfg.remove(pid)
        for p in self._people:
            self.cfg.upsert(p)
        if not self.cfg.person(self.cfg.get("active_id", "")) and self.cfg.people:
            self.cfg.set_active(self.cfg.people[0]["id"])
