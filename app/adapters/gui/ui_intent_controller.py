"""Facade module preserving the public UiIntentController import path.

Split across `ui_intent_controller_*.py` mixin files (see docs/ARCHITEKTUR.md
and the file-size-split plan) to stay under the project's ~300-line-of-code
convention. Internal mixin files import their own dependencies directly from
their source modules (e.g. `app.adapters.gui.dialog_services`), never from
this facade - this facade exists for external callers/tests only.
"""

from __future__ import annotations

from app.adapters.gui.dialog_services import filedialog, messagebox, simpledialog  # noqa: F401 - re-exported: tests patch uic_module.messagebox

from app.adapters.gui.ui_intent_controller_annotations import UiIntentControllerAnnotationsMixin
from app.adapters.gui.ui_intent_controller_base import UiIntentControllerBase
from app.adapters.gui.ui_intent_controller_completion import UiIntentControllerCompletionMixin
from app.adapters.gui.ui_intent_controller_grading_scale import UiIntentControllerGradingScaleMixin
from app.adapters.gui.ui_intent_controller_history import UiIntentControllerHistoryMixin
from app.adapters.gui.ui_intent_controller_naming import UiIntentControllerNamingMixin
from app.adapters.gui.ui_intent_controller_overview import UiIntentControllerOverviewMixin
from app.adapters.gui.ui_intent_controller_regions import UiIntentControllerRegionsMixin
from app.adapters.gui.ui_intent_controller_scoring import UiIntentControllerScoringMixin
from app.adapters.gui.ui_intent_controller_superposition import UiIntentControllerSuperpositionMixin
from app.adapters.gui.ui_intent_controller_supersymbol import UiIntentControllerSupersymbolMixin


class UiIntentController(
    UiIntentControllerAnnotationsMixin,
    UiIntentControllerGradingScaleMixin,
    UiIntentControllerSuperpositionMixin,
    UiIntentControllerSupersymbolMixin,
    UiIntentControllerNamingMixin,
    UiIntentControllerCompletionMixin,
    UiIntentControllerRegionsMixin,
    UiIntentControllerScoringMixin,
    UiIntentControllerOverviewMixin,
    UiIntentControllerHistoryMixin,
    UiIntentControllerBase,
):
    """GUI-facing orchestration layer wrapping use-cases/repositories."""
