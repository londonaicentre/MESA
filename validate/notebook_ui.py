import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Callable

import ipywidgets as widgets

from mesa_validate.models import FieldSelection, Session
from mesa_validate.predictions_loader import load_prediction_file
from mesa_validate.schema_inspector import SchemaInspector
from mesa_validate.selection_resolver import (
    encode_binary_result,
    encode_list_item_result,
    is_value_present,
    map_storage_to_ui,
    resolve_selection,
)
from mesa_validate.session_manager import SessionManager


@dataclass
class ReviewBlock:
    widget: widgets.DOMWidget
    encode: Callable[[], object]


class DocumentReviewer(widgets.VBox):
    """
    Human-in-the-loop review widget for a validation session

    Args:
        session (Session): Session being reviewed
        inspector (SchemaInspector): SchemaInspector for the session's schema
        manager (SessionManager): SessionManager for loading/saving progress
        progress (dict[str, Any]): Progress dict, as returned by
            `manager.initialize_files`
        excluded (dict[str, str]): Dict of document_id to exclusion reason,
            from the same call
    """

    def __init__(
        self,
        session: Session,
        inspector: SchemaInspector,
        manager: SessionManager,
        progress: dict[str, Any],
        excluded: dict[str, str],
    ) -> None:
        super().__init__()
        self.session: Session = session
        self.inspector: SchemaInspector = inspector
        self.manager: SessionManager = manager
        self.progress: dict[str, Any] = progress
        self.excluded: dict[str, str] = excluded
        self._blocks: dict[str, ReviewBlock] = {}
        self._complete_checkbox: widgets.Checkbox | None = None
        self._render()

    def _render(self) -> None:
        files: list[str] = self.progress["files"]

        if not files:
            self.children = [
                widgets.HTML("No valid documents to review."),
                *[
                    widgets.HTML(f"excluded {document_id}: {reason}")
                    for document_id, reason in self.excluded.items()
                ],
            ]
            return

        index: int = self.progress["current_file_index"]
        document_id: str = files[index]
        prediction: dict[str, Any] = load_prediction_file(
            document_id, self.session.predictions_folder
        )
        extraction_data: dict[str, Any] = prediction["document_inference"]
        existing_results: dict[str, Any] = self.progress["results"].get(document_id, {})

        completed_files: list[str] = self.progress.get("completed_files", [])
        header: widgets.HTML = widgets.HTML(
            f"<h4>Document {index + 1} of {len(files)} — {document_id}</h4>"
            f"<p>Completed: {len(completed_files)}/{len(files)}</p>"
        )

        document_pane: widgets.VBox = widgets.VBox(
            [
                widgets.HTML("<b>Document</b>"),
                widgets.Textarea(
                    value=prediction.get("document_content") or "(no document content)",
                    layout=widgets.Layout(width="500px", height="600px"),
                    disabled=True,
                ),
            ],
            layout=widgets.Layout(flex="0 0 auto", margin="0 20px 0 0"),
        )

        self._blocks = {}
        validation_items: list[widgets.DOMWidget] = [widgets.HTML("<b>Validation</b>")]

        if not extraction_data:
            validation_items.append(widgets.HTML("<b>No extraction data available</b>"))
        else:
            for selection in self.session.selections:
                key: str = selection.build_key()
                try:
                    result: dict[str, Any] = resolve_selection(
                        selection, extraction_data, self.inspector
                    )
                except ValueError as e:
                    validation_items.append(
                        widgets.HTML(f"<b>{self._selection_title(selection)}</b>: {e}")
                    )
                    continue

                block: ReviewBlock = self._build_review_block(
                    result, existing_results.get(key)
                )
                validation_items.append(
                    widgets.HTML(f"<b>{self._selection_title(selection)}</b>")
                )
                validation_items.append(block.widget)
                self._blocks[key] = block

        self._complete_checkbox = widgets.Checkbox(
            value=document_id in completed_files,
            description="Mark document as fully validated",
        )
        validation_items.append(self._complete_checkbox)

        for validation_item in validation_items:
            validation_item.layout.flex = "0 0 auto"

        validation_pane: widgets.VBox = widgets.VBox(
            validation_items,
            layout=widgets.Layout(
                width="520px", height="600px", overflow="auto", flex="0 0 auto"
            ),
        )

        previous_button: widgets.Button = widgets.Button(
            description="Save & Previous", disabled=index == 0
        )
        save_button: widgets.Button = widgets.Button(description="Save")
        next_button: widgets.Button = widgets.Button(
            description="Save & Next", disabled=index == len(files) - 1
        )
        previous_button.on_click(lambda _: self._save_and_move(-1))
        save_button.on_click(lambda _: self._save_and_move(0))
        next_button.on_click(lambda _: self._save_and_move(1))

        self.children = [
            header,
            widgets.HBox(
                [document_pane, validation_pane],
                layout=widgets.Layout(align_items="flex-start"),
            ),
            widgets.HBox([previous_button, save_button, next_button]),
        ]

    def _save_and_move(self, direction: int) -> None:
        assert self._complete_checkbox is not None
        document_id: str = self.progress["files"][self.progress["current_file_index"]]
        non_none_results: dict[str, object] = {
            key: value
            for key, block in self._blocks.items()
            if (value := block.encode()) is not None and value != "NONE"
        }
        self.progress = self.manager.save_results(document_id, non_none_results)

        completed_files: list[str] = self.progress.setdefault("completed_files", [])
        if self._complete_checkbox.value and document_id not in completed_files:
            completed_files.append(document_id)
        elif not self._complete_checkbox.value and document_id in completed_files:
            completed_files.remove(document_id)

        new_index: int = self.progress["current_file_index"] + direction
        self.progress["current_file_index"] = max(
            0, min(new_index, len(self.progress["files"]) - 1)
        )

        self.manager.save_progress(self.progress)
        self._render()

    @staticmethod
    def _build_review_block(
        result: dict[str, Any], current_value: object
    ) -> ReviewBlock:
        if not result["is_list"]:
            item: object = result["items"][0]
            is_present: bool = is_value_present(item)
            radio: widgets.RadioButtons = widgets.RadioButtons(
                options=["None", "Correct", "Incorrect"],
                value=DocumentReviewer._default_choice(current_value),
            )
            panel: widgets.VBox = widgets.VBox(
                [
                    widgets.HTML(f"<pre>{DocumentReviewer._format_item(item)}</pre>"),
                    radio,
                ]
            )
            return ReviewBlock(
                panel, lambda: encode_binary_result(radio.value, is_present)
            )

        current_items: Sequence[object] = []
        current_missed: int = 0
        if isinstance(current_value, dict):
            items_value: object = current_value.get("items", [])
            if isinstance(items_value, list):
                current_items = items_value
            missed_value: object = current_value.get("missed", 0)
            if isinstance(missed_value, int):
                current_missed = missed_value

        item_radios: list[widgets.RadioButtons] = []
        rows: list[widgets.DOMWidget] = []
        for index, item in enumerate(result["items"]):
            saved: object = current_items[index] if index < len(current_items) else None
            default: str = (
                "Correct"
                if saved is True
                else "Incorrect"
                if saved is False
                else "None"
            )
            radio = widgets.RadioButtons(
                options=["None", "Correct", "Incorrect"], value=default
            )
            item_radios.append(radio)
            rows.append(
                widgets.VBox(
                    [
                        widgets.HTML(
                            f"<pre>Item {index + 1}: {DocumentReviewer._format_item(item)}</pre>"
                        ),
                        radio,
                    ]
                )
            )

        if not result["items"]:
            rows.append(widgets.HTML("<i>No items found in prediction</i>"))

        missed_input: widgets.IntText = widgets.IntText(
            value=current_missed, description="Missed:"
        )
        panel = widgets.VBox(rows + [missed_input])

        def encode() -> dict[str, object]:
            return {
                "items": [
                    encode_list_item_result(radio.value) for radio in item_radios
                ],
                "missed": missed_input.value,
            }

        return ReviewBlock(panel, encode)

    @staticmethod
    def _selection_title(selection: FieldSelection) -> str:
        if selection.selection_type == "basemodel_class":
            return f"{selection.class_name} (class)"
        if selection.selection_type == "basemodel_field":
            return f"{selection.class_name}.{selection.field_name}"
        return f"{selection.class_name}.{selection.enum_value}"

    @staticmethod
    def _format_item(item: object) -> str:
        return (
            json.dumps(item, indent=2) if isinstance(item, (dict, list)) else str(item)
        )

    @staticmethod
    def _default_choice(storage_value: object) -> str:
        mapped: str = map_storage_to_ui(storage_value) if storage_value else "NONE"
        return {"CORRECT": "Correct", "INCORRECT": "Incorrect"}.get(mapped, "None")
