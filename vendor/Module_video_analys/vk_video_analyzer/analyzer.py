from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .config import AnalyzerConfig
from .detectors import Detection, OptionalTemplateMatcher, YoloDetector, choose_available_person_weights
from .heuristics import (
    brightness_stats,
    crop,
    detect_avatar,
    detect_black_screen,
    detect_empty_room,
    detect_fullscreen_avatar,
    detect_low_quality,
    detect_screen_share,
    histogram_signature,
    histogram_similarity,
    mse_similarity,
    split_layout,
)
from .schemas import (
    AnalysisResult,
    DECISION_TITLES_RU,
    FLAG_TITLES_RU,
    FrameObservation,
    SITUATIONS,
    SITUATION_DESCRIPTIONS_RU,
    SITUATIONS_RU,
    STATE_TITLES_RU,
    SegmentRecord,
)


class VideoAnalyzer:
    def __init__(self, config: AnalyzerConfig | None = None, person_detector: YoloDetector | None = None) -> None:
        self.config = config or AnalyzerConfig()
        self.person_detector = person_detector or choose_available_person_weights(
            self.config.person_weights_candidates,
            device=self.config.device,
            conf=self.config.person_confidence,
        )
        self.layout_detector = (
            YoloDetector(self.config.layout_weights, device=self.config.device, conf=self.config.person_confidence)
            if self.config.layout_weights
            else None
        )
        self.mute_matcher = OptionalTemplateMatcher(self.config.mute_templates_dir)

    def analyze(self, video_path: str | Path) -> AnalysisResult:
        video_path = Path(video_path)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_sec = float(frame_count / fps) if fps > 0 else 0.0
        sample_step = max(1, int(round(fps * self.config.sample_interval_sec)))

        observations: list[FrameObservation] = []
        previous_main_roi: np.ndarray | None = None
        previous_hist: np.ndarray | None = None
        freeze_streak_sec = 0.0
        frame_index = 0

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % sample_step != 0:
                frame_index += 1
                continue

            timestamp_sec = frame_index / fps if fps > 0 else 0.0
            observation, previous_main_roi, previous_hist, freeze_streak_sec = self._analyze_frame(
                frame=frame,
                timestamp_sec=timestamp_sec,
                previous_main_roi=previous_main_roi,
                previous_hist=previous_hist,
                freeze_streak_sec=freeze_streak_sec,
            )
            observations.append(observation)
            frame_index += 1

        capture.release()
        segments = self._build_segments(observations, duration_sec)
        summary = self._build_summary(video_path, duration_sec, fps, observations, segments)
        result = AnalysisResult(
            video={
                "path": str(video_path),
                "duration_sec": round(duration_sec, 3),
                "fps": round(fps, 3),
                "frame_count": frame_count,
                "sample_interval_sec": self.config.sample_interval_sec,
            },
            summary=summary,
            segments=segments,
            observations=observations if self.config.save_observations else [],
        )
        return result

    def analyze_to_json(
        self,
        video_path: str | Path,
        output_path: str | Path,
        indent: int = 2,
        output_format: str = "alerts",
        only_on_problem: bool = False,
    ) -> AnalysisResult:
        result = self.analyze(video_path)
        output_payload = result.to_dict(output_format=output_format)
        if only_on_problem:
            if output_format == "alerts" and not output_payload.get("проблемы"):
                return result
            if output_format == "events":
                has_problem_events = any(
                    event.get("тип_события") == "проблема_обнаружена"
                    for event in output_payload.get("события", [])
                )
                if not has_problem_events:
                    return result

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=indent), encoding="utf-8")
        return result

    def analyze_to_live_jsonl(
        self,
        video_path: str | Path,
        output_path: str | Path,
        only_on_problem: bool = False,
    ) -> AnalysisResult:
        video_path = Path(video_path)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        fps = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration_sec = float(frame_count / fps) if fps > 0 else 0.0
        sample_step = max(1, int(round(fps * self.config.sample_interval_sec)))

        video_info = {
            "path": str(video_path),
            "duration_sec": round(duration_sec, 3),
            "fps": round(fps, 3),
            "frame_count": frame_count,
            "sample_interval_sec": self.config.sample_interval_sec,
        }
        writer = _LiveJsonlWriter(Path(output_path), only_on_problem=only_on_problem)

        observations: list[FrameObservation] = []
        previous_main_roi: np.ndarray | None = None
        previous_hist: np.ndarray | None = None
        freeze_streak_sec = 0.0
        frame_index = 0
        segment_start_index = 0
        active_problem_segment_start: float | None = None
        active_problem_payload: dict[str, Any] | None = None
        event_id = 1

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % sample_step != 0:
                frame_index += 1
                continue

            timestamp_sec = frame_index / fps if fps > 0 else 0.0
            observation, previous_main_roi, previous_hist, freeze_streak_sec = self._analyze_frame(
                frame=frame,
                timestamp_sec=timestamp_sec,
                previous_main_roi=previous_main_roi,
                previous_hist=previous_hist,
                freeze_streak_sec=freeze_streak_sec,
            )
            observations.append(observation)
            current_index = len(observations) - 1
            current_end_sec = observation.timestamp_sec + self.config.sample_interval_sec

            if current_index > segment_start_index and not self._same_segment(observations[segment_start_index], observation):
                previous_segment = self._segment_from_range(
                    observations=observations,
                    start_index=segment_start_index,
                    end_index=current_index - 1,
                    duration_sec=observation.timestamp_sec,
                )

                if active_problem_segment_start == previous_segment.start_sec and active_problem_payload is not None:
                    next_segment = self._segment_from_range(
                        observations=observations,
                        start_index=current_index,
                        end_index=current_index,
                        duration_sec=current_end_sec,
                    )
                    writer.write(
                        self._build_live_problem_resolved_event_ru(
                            event_id=event_id,
                            timestamp_sec=previous_segment.end_sec,
                            previous_problem=active_problem_payload,
                            next_segment=next_segment,
                        )
                    )
                    event_id += 1
                    active_problem_segment_start = None
                    active_problem_payload = None

                segment_start_index = current_index

            current_segment = self._segment_from_range(
                observations=observations,
                start_index=segment_start_index,
                end_index=current_index,
                duration_sec=current_end_sec,
            )
            if self._segment_is_problem(current_segment) and active_problem_segment_start != current_segment.start_sec:
                active_problem_payload = self._segment_to_problem_payload_ru(current_segment)
                writer.write(
                    self._build_live_problem_detected_event_ru(
                        event_id=event_id,
                        timestamp_sec=observation.timestamp_sec,
                        segment=current_segment,
                        problem_payload=active_problem_payload,
                    )
                )
                event_id += 1
                active_problem_segment_start = current_segment.start_sec

            frame_index += 1

        capture.release()
        segments = self._build_segments(observations, duration_sec)
        summary = self._build_summary(video_path, duration_sec, fps, observations, segments)
        writer.write(
            self._build_live_finish_event_ru(
                event_id=event_id,
                video_info=video_info,
                summary=summary,
            )
        )
        writer.close()

        return AnalysisResult(
            video=video_info,
            summary=summary,
            segments=segments,
            observations=observations if self.config.save_observations else [],
        )

    def build_live_events_from_observations(
        self,
        video_path: str | Path,
        duration_sec: float,
        fps: float,
        observations: list[FrameObservation],
    ) -> list[dict[str, Any]]:
        if not observations:
            summary = self._build_summary(Path(video_path), duration_sec, fps, observations, [])
            return [
                self._build_live_finish_event_ru(
                    event_id=1,
                    video_info={
                        "path": str(video_path),
                        "duration_sec": round(duration_sec, 3),
                        "fps": round(fps, 3),
                        "frame_count": 0,
                        "sample_interval_sec": self.config.sample_interval_sec,
                    },
                    summary=summary,
                )
            ]

        events: list[dict[str, Any]] = []
        segment_start_index = 0
        active_problem_segment_start: float | None = None
        active_problem_payload: dict[str, Any] | None = None
        event_id = 1

        for current_index, observation in enumerate(observations):
            current_end_sec = observation.timestamp_sec + self.config.sample_interval_sec

            if current_index > segment_start_index and not self._same_segment(observations[segment_start_index], observation):
                previous_segment = self._segment_from_range(
                    observations=observations,
                    start_index=segment_start_index,
                    end_index=current_index - 1,
                    duration_sec=observation.timestamp_sec,
                )
                if active_problem_segment_start == previous_segment.start_sec and active_problem_payload is not None:
                    next_segment = self._segment_from_range(
                        observations=observations,
                        start_index=current_index,
                        end_index=current_index,
                        duration_sec=current_end_sec,
                    )
                    events.append(
                        self._build_live_problem_resolved_event_ru(
                            event_id=event_id,
                            timestamp_sec=previous_segment.end_sec,
                            previous_problem=active_problem_payload,
                            next_segment=next_segment,
                        )
                    )
                    event_id += 1
                    active_problem_segment_start = None
                    active_problem_payload = None
                segment_start_index = current_index

            current_segment = self._segment_from_range(
                observations=observations,
                start_index=segment_start_index,
                end_index=current_index,
                duration_sec=current_end_sec,
            )
            if self._segment_is_problem(current_segment) and active_problem_segment_start != current_segment.start_sec:
                active_problem_payload = self._segment_to_problem_payload_ru(current_segment)
                events.append(
                    self._build_live_problem_detected_event_ru(
                        event_id=event_id,
                        timestamp_sec=observation.timestamp_sec,
                        segment=current_segment,
                        problem_payload=active_problem_payload,
                    )
                )
                event_id += 1
                active_problem_segment_start = current_segment.start_sec

        segments = self._build_segments(observations, duration_sec)
        summary = self._build_summary(Path(video_path), duration_sec, fps, observations, segments)
        events.append(
            self._build_live_finish_event_ru(
                event_id=event_id,
                video_info={
                    "path": str(video_path),
                    "duration_sec": round(duration_sec, 3),
                    "fps": round(fps, 3),
                    "frame_count": 0,
                    "sample_interval_sec": self.config.sample_interval_sec,
                },
                summary=summary,
            )
        )
        return events

    def _analyze_frame(
        self,
        frame: np.ndarray,
        timestamp_sec: float,
        previous_main_roi: np.ndarray | None,
        previous_hist: np.ndarray | None,
        freeze_streak_sec: float,
    ) -> tuple[FrameObservation, np.ndarray, np.ndarray, float]:
        if frame.shape[1] < self.config.min_window_width or frame.shape[0] < self.config.min_window_height:
            observation = FrameObservation(
                timestamp_sec=round(timestamp_sec, 3),
                primary_state="window_not_found",
                confidence=1.0,
                flags=self._default_flags(window_not_found=True),
                reasons=["Frame is smaller than the minimum expected broadcast window size."],
            )
            next_frame = previous_main_roi if previous_main_roi is not None else frame
            next_hist = previous_hist if previous_hist is not None else histogram_signature(frame)
            return observation, next_frame, next_hist, 0.0

        layout = split_layout(frame, self.config)
        main_roi = crop(frame, layout.main_region)
        teacher_tile_roi = crop(frame, layout.teacher_tile_region)

        detections = self.person_detector.detect(frame)
        custom_detections = self.layout_detector.detect(frame) if self.layout_detector else []

        teacher_main_area_ratio = self._max_area_ratio(detections, layout.main_region, "person", layout.main_region)
        teacher_tile_area_ratio = self._max_area_ratio(detections, layout.teacher_tile_region, "person", layout.teacher_tile_region)

        teacher_in_main = teacher_main_area_ratio >= self.config.teacher_main_min_area_ratio
        person_in_tile = teacher_tile_area_ratio >= self.config.teacher_tile_min_area_ratio
        black_screen = detect_black_screen(main_roi, self.config)
        low_quality = detect_low_quality(main_roi, self.config)
        fullscreen_avatar = detect_fullscreen_avatar(main_roi, teacher_main_area_ratio, self.config)
        avatar_visible = (
            self._detect_avatar(
                teacher_tile_roi=teacher_tile_roi,
                teacher_tile_region=layout.teacher_tile_region,
                teacher_tile_area_ratio=teacher_tile_area_ratio,
                custom_detections=custom_detections,
            )
            or fullscreen_avatar
        )
        screen_share = self._detect_screen_share(
            main_roi=main_roi,
            main_region=layout.main_region,
            teacher_in_main=teacher_in_main,
            custom_detections=custom_detections,
        )

        hist = histogram_signature(main_roi)
        frozen_frame = False
        if previous_main_roi is not None and previous_hist is not None and previous_main_roi.shape == main_roi.shape:
            mse_value = mse_similarity(main_roi, previous_main_roi)
            hist_similarity = histogram_similarity(hist, previous_hist)
            if mse_value <= self.config.freeze_mse_threshold and hist_similarity >= self.config.freeze_hist_threshold:
                freeze_streak_sec += self.config.sample_interval_sec
            else:
                freeze_streak_sec = 0.0
            frozen_frame = freeze_streak_sec >= self.config.freeze_min_duration_sec
        else:
            mse_value = 0.0
            hist_similarity = 0.0
            freeze_streak_sec = 0.0

        if avatar_visible or screen_share or black_screen:
            freeze_streak_sec = 0.0
            frozen_frame = False

        empty_room = detect_empty_room(main_roi, screen_share=screen_share, black_screen=black_screen)
        muted_icon = self._detect_muted_icon(teacher_tile_roi, custom_detections)

        primary_state, confidence, reasons = self._decide_primary_state(
            teacher_in_main=teacher_in_main,
            screen_share=screen_share,
            avatar_visible=avatar_visible,
            fullscreen_avatar=fullscreen_avatar,
            black_screen=black_screen,
            frozen_frame=frozen_frame,
            low_quality=low_quality,
            empty_room=empty_room,
        )

        flags = self._default_flags(
            teacher_in_main=teacher_in_main,
            screen_share=screen_share,
            avatar_visible=avatar_visible,
            muted_icon=muted_icon,
            empty_room=empty_room,
            black_screen=black_screen,
            frozen_frame=frozen_frame,
            low_quality=low_quality,
            person_in_tile=person_in_tile,
            fullscreen_avatar=fullscreen_avatar,
        )
        if muted_icon:
            reasons.append("Muted microphone icon detected in the teacher tile.")

        mean_value, std_value = brightness_stats(main_roi)
        metrics = {
            "teacher_main_area_ratio": round(teacher_main_area_ratio, 6),
            "teacher_tile_area_ratio": round(teacher_tile_area_ratio, 6),
            "brightness_mean": round(mean_value, 4),
            "brightness_std": round(std_value, 4),
            "freeze_streak_sec": round(freeze_streak_sec, 3),
            "mse_value": round(mse_value, 6),
            "hist_similarity": round(hist_similarity, 6),
            "fullscreen_avatar": float(fullscreen_avatar),
        }

        observation = FrameObservation(
            timestamp_sec=round(timestamp_sec, 3),
            primary_state=primary_state,
            confidence=confidence,
            flags=flags,
            reasons=reasons,
            metrics=metrics,
        )
        return observation, main_roi.copy(), hist, freeze_streak_sec

    def _build_segments(self, observations: list[FrameObservation], duration_sec: float) -> list[SegmentRecord]:
        if not observations:
            return []

        segments: list[SegmentRecord] = []
        start_index = 0
        for index in range(1, len(observations)):
            if not self._same_segment(observations[start_index], observations[index]):
                segments.append(self._segment_from_range(observations, start_index, index - 1, duration_sec))
                start_index = index
        segments.append(self._segment_from_range(observations, start_index, len(observations) - 1, duration_sec))
        return segments

    def _segment_from_range(
        self,
        observations: list[FrameObservation],
        start_index: int,
        end_index: int,
        duration_sec: float,
    ) -> SegmentRecord:
        start_time = observations[start_index].timestamp_sec
        if end_index + 1 < len(observations):
            end_time = observations[end_index + 1].timestamp_sec
        else:
            end_time = duration_sec
        duration = max(0.0, end_time - start_time)
        segment_observations = observations[start_index : end_index + 1]
        flags = self._aggregate_flags(segment_observations)
        confidence = round(sum(item.confidence for item in segment_observations) / len(segment_observations), 3)
        situation_ids, decision, reasons = self._decorate_segment(
            primary_state=observations[start_index].primary_state,
            start_time=start_time,
            duration_sec=duration,
            flags=flags,
        )
        inherited_reasons: list[str] = []
        for observation in segment_observations[:3]:
            inherited_reasons.extend(observation.reasons[:2])

        return SegmentRecord(
            start_sec=round(start_time, 3),
            end_sec=round(end_time, 3),
            duration_sec=round(duration, 3),
            primary_state=observations[start_index].primary_state,
            situation_ids=situation_ids,
            decision=decision,
            confidence=confidence,
            flags=flags,
            reasons=self._deduplicate_reasons(inherited_reasons + reasons),
        )

    def _decorate_segment(
        self,
        primary_state: str,
        start_time: float,
        duration_sec: float,
        flags: dict[str, bool],
    ) -> tuple[list[int], str, list[str]]:
        reasons: list[str] = []
        situation_ids: list[int]
        decision: str

        if primary_state == "teacher_present":
            situation_ids = [1]
            decision = "class_in_progress"
            reasons.append("Teacher is visible in the main broadcast area.")
        elif primary_state == "screen_share":
            situation_ids = [2]
            decision = "class_in_progress"
            reasons.append("Screen sharing pattern is visible in the main area.")
        elif primary_state == "teacher_missing":
            if duration_sec < self.config.short_absence_sec:
                situation_ids = [3]
                decision = "class_in_progress"
                reasons.append("Teacher disappeared only for a short time.")
            elif start_time < self.config.first_five_minutes_sec and duration_sec >= self.config.long_absence_early_sec:
                situation_ids = [4]
                decision = "possible_problem"
                reasons.append("Teacher has been absent for a long time during the first 5 minutes.")
            elif start_time >= self.config.first_five_minutes_sec and duration_sec >= self.config.long_absence_late_sec:
                situation_ids = [5]
                decision = "likely_finished"
                reasons.append("Absence continued for more than the configured threshold after the first 5 minutes.")
            else:
                situation_ids = [3]
                decision = "possible_problem"
                reasons.append("Teacher is absent longer than usual, but not enough to close the lesson confidently.")
        elif primary_state == "camera_off_avatar":
            if duration_sec < self.config.long_avatar_sec:
                situation_ids = [6]
                decision = "class_in_progress"
                reasons.append("Only the teacher avatar is visible.")
            elif start_time <= self.config.sample_interval_sec and duration_sec <= self.config.initial_avatar_grace_sec:
                situation_ids = [6]
                decision = "class_in_progress"
                reasons.append("The broadcast likely just started and only the teacher avatar is visible so far.")
            elif start_time < self.config.normal_lesson_min_sec:
                situation_ids = [7]
                decision = "possible_problem"
                reasons.append("Teacher avatar remained visible for a long time during the lesson.")
            else:
                situation_ids = [8]
                decision = "likely_finished"
                reasons.append("Teacher avatar remained after the normal lesson minimum duration.")
        elif primary_state == "empty_room":
            situation_ids = [12]
            decision = "likely_finished" if start_time >= self.config.first_five_minutes_sec else "possible_problem"
            reasons.append("The scene looks like an empty room or workplace without the teacher.")
        elif primary_state == "black_screen":
            situation_ids = [10]
            if duration_sec < self.config.black_screen_problem_min_sec:
                decision = "class_in_progress"
                reasons.append("A short black-screen transition was detected, but it is too short to count as a problem.")
            else:
                decision = "technical_issue"
                reasons.append("The main area is almost entirely black for too long.")
        elif primary_state == "frozen_frame":
            situation_ids = [11]
            decision = "technical_issue"
            reasons.append("The frame looks frozen for longer than the configured threshold.")
        elif primary_state == "low_quality":
            situation_ids = [13]
            decision = "technical_issue"
            reasons.append("Image is too dark or blurry for reliable analysis.")
        else:
            situation_ids = [14]
            decision = "technical_issue"
            reasons.append("Broadcast window could not be identified correctly.")

        if flags.get("muted_icon"):
            situation_ids = sorted(set(situation_ids + [9]))
            if decision == "class_in_progress":
                decision = "class_in_progress_with_issues"
            reasons.append("Muted microphone icon indicates a possible audio problem.")

        return situation_ids, decision, reasons

    def _build_summary(
        self,
        video_path: Path,
        duration_sec: float,
        fps: float,
        observations: list[FrameObservation],
        segments: list[SegmentRecord],
    ) -> dict[str, Any]:
        situation_counter = Counter()
        state_duration: Counter[str] = Counter()
        issue_segments: list[dict[str, Any]] = []

        for segment in segments:
            for situation_id in segment.situation_ids:
                situation_counter[SITUATIONS[situation_id]] += segment.duration_sec
            state_duration[segment.primary_state] += segment.duration_sec
            if 9 in segment.situation_ids or segment.decision in {"technical_issue", "possible_problem"}:
                issue_segments.append(asdict(segment))

        sidebar_avatar_teaching_sec = sum(
            segment.duration_sec
            for segment in segments
            if segment.primary_state == "camera_off_avatar" and not segment.flags.get("fullscreen_avatar", False)
        )
        confident_teaching_sec = round(
            state_duration.get("teacher_present", 0.0)
            + state_duration.get("screen_share", 0.0)
            + state_duration.get("empty_room", 0.0)
            + sidebar_avatar_teaching_sec,
            3,
        )
        possible_teaching_sec = round(
            confident_teaching_sec
            + state_duration.get("camera_off_avatar", 0.0)
            + state_duration.get("teacher_missing", 0.0),
            3,
        )

        final_decision = segments[-1].decision if segments else "no_data"
        final_state = segments[-1].primary_state if segments else "no_data"
        summary_primary_state = self._choose_summary_primary_state(
            state_duration=state_duration,
            final_state=final_state,
            final_decision=final_decision,
        )

        return {
            "video_name": video_path.name,
            "duration_sec": round(duration_sec, 3),
            "fps": round(fps, 3),
            "sample_count": len(observations),
            "summary_primary_state": summary_primary_state,
            "final_primary_state": final_state,
            "final_decision": final_decision,
            "confident_teaching_sec": confident_teaching_sec,
            "possible_teaching_sec": possible_teaching_sec,
            "situation_durations_sec": {key: round(value, 3) for key, value in situation_counter.items()},
            "primary_state_durations_sec": {key: round(value, 3) for key, value in state_duration.items()},
            "issue_segments": issue_segments,
        }

    def _choose_summary_primary_state(
        self,
        state_duration: Counter[str],
        final_state: str,
        final_decision: str,
    ) -> str:
        if not state_duration:
            return final_state

        teaching_states = ("screen_share", "teacher_present")
        teaching_durations = {state: state_duration.get(state, 0.0) for state in teaching_states}
        dominant_teaching_state, dominant_teaching_duration = max(
            teaching_durations.items(),
            key=lambda item: item[1],
        )

        if dominant_teaching_duration > 0 and final_decision in {"class_in_progress", "likely_finished"}:
            final_duration = state_duration.get(final_state, 0.0)
            if dominant_teaching_duration >= final_duration:
                return dominant_teaching_state

        return max(state_duration.items(), key=lambda item: item[1])[0]

    def _segment_to_problem_payload_ru(self, segment: SegmentRecord) -> dict[str, Any]:
        situation_titles = [SITUATIONS_RU.get(situation_id, str(situation_id)) for situation_id in segment.situation_ids]
        descriptions = [SITUATION_DESCRIPTIONS_RU.get(situation_id, "") for situation_id in segment.situation_ids]
        return {
            "тип": situation_titles[0] if situation_titles else STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
            "уровень": self._severity_ru_live(segment.decision),
            "начало_сек": segment.start_sec,
            "конец_сек": segment.end_sec,
            "длительность_сек": segment.duration_sec,
            "состояние": STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
            "решение": DECISION_TITLES_RU.get(segment.decision, segment.decision),
            "ситуации": situation_titles,
            "описание": " ".join(item for item in descriptions if item),
            "признаки": self._true_flags_ru_live(segment.flags),
            "уверенность": segment.confidence,
        }

    @staticmethod
    def _segment_is_problem(segment: SegmentRecord) -> bool:
        return segment.decision in {"class_in_progress_with_issues", "possible_problem", "technical_issue"}

    def _build_live_problem_detected_event_ru(
        self,
        event_id: int,
        timestamp_sec: float,
        segment: SegmentRecord,
        problem_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "версия": 2,
            "ид": event_id,
            "тип_события": "проблема_обнаружена",
            "время_сек": round(timestamp_sec, 3),
            "состояние": STATE_TITLES_RU.get(segment.primary_state, segment.primary_state),
            "решение": DECISION_TITLES_RU.get(segment.decision, segment.decision),
            "проблема": problem_payload,
        }

    def _build_live_problem_resolved_event_ru(
        self,
        event_id: int,
        timestamp_sec: float,
        previous_problem: dict[str, Any],
        next_segment: SegmentRecord,
    ) -> dict[str, Any]:
        return {
            "версия": 2,
            "ид": event_id,
            "тип_события": "проблема_устранена",
            "время_сек": round(timestamp_sec, 3),
            "предыдущая_проблема": previous_problem["тип"],
            "новое_состояние": STATE_TITLES_RU.get(next_segment.primary_state, next_segment.primary_state),
            "новое_решение": DECISION_TITLES_RU.get(next_segment.decision, next_segment.decision),
        }

    def _build_live_finish_event_ru(
        self,
        event_id: int,
        video_info: dict[str, Any],
        summary: dict[str, Any],
    ) -> dict[str, Any]:
        final_decision = str(summary.get("final_decision", "no_data"))
        final_state = str(summary.get("final_primary_state", "no_data"))
        summary_state = str(summary.get("summary_primary_state", final_state))
        has_active_problem = final_decision in {"class_in_progress_with_issues", "possible_problem", "technical_issue"}
        return {
            "версия": 2,
            "ид": event_id,
            "тип_события": "трансляция_завершена",
            "время_сек": video_info.get("duration_sec"),
            "итог": {
                "статус": self._summary_status_ru_live(
                    has_problems=bool(summary.get("issue_segments")),
                    final_decision=final_decision,
                ),
                "состояние_трансляции": DECISION_TITLES_RU.get(final_decision, final_decision),
                "основное_состояние": STATE_TITLES_RU.get(summary_state, summary_state),
                "есть_актуальная_проблема": has_active_problem,
            },
        }

    def _decide_primary_state(
        self,
        teacher_in_main: bool,
        screen_share: bool,
        avatar_visible: bool,
        fullscreen_avatar: bool,
        black_screen: bool,
        frozen_frame: bool,
        low_quality: bool,
        empty_room: bool,
    ) -> tuple[str, float, list[str]]:
        reasons: list[str] = []
        if black_screen:
            reasons.append("Black-screen threshold reached.")
            return "black_screen", 0.98, reasons
        if screen_share:
            reasons.append("Screen-share heuristics matched.")
            return "screen_share", 0.82, reasons
        if teacher_in_main:
            reasons.append("YOLO detected a person in the main content area.")
            return "teacher_present", 0.9, reasons
        if empty_room and not fullscreen_avatar:
            reasons.append("The main area looks like a room or board without a person.")
            return "empty_room", 0.74, reasons
        if avatar_visible:
            reasons.append("Teacher tile looks like an avatar instead of live video.")
            return "camera_off_avatar", 0.8, reasons
        if frozen_frame:
            reasons.append("Freeze thresholds reached.")
            return "frozen_frame", 0.95, reasons
        if low_quality:
            reasons.append("Dark or blurry image limits reliable classification.")
            return "low_quality", 0.68, reasons
        reasons.append("No teacher detected in the main area.")
        return "teacher_missing", 0.72, reasons

    def _detect_screen_share(
        self,
        main_roi: np.ndarray,
        main_region: tuple[int, int, int, int],
        teacher_in_main: bool,
        custom_detections: list[Detection],
    ) -> bool:
        if self._has_detection_in_region(custom_detections, {"screen_share", "presentation", "desktop"}, main_region):
            return True
        return detect_screen_share(main_roi, teacher_in_main, self.config)

    def _detect_avatar(
        self,
        teacher_tile_roi: np.ndarray,
        teacher_tile_region: tuple[int, int, int, int],
        teacher_tile_area_ratio: float,
        custom_detections: list[Detection],
    ) -> bool:
        if self._has_detection_in_region(custom_detections, {"teacher_avatar", "avatar"}, teacher_tile_region):
            return True
        return detect_avatar(teacher_tile_roi, teacher_tile_area_ratio, self.config)

    def _detect_muted_icon(self, teacher_tile_roi: np.ndarray, custom_detections: list[Detection]) -> bool:
        if any(item.class_name in {"mute_icon", "muted_microphone"} for item in custom_detections):
            return True
        score = self.mute_matcher.match(teacher_tile_roi)
        return score > 0.0

    def _max_area_ratio(
        self,
        detections: list[Detection],
        filter_region: tuple[int, int, int, int],
        class_name: str,
        normalization_region: tuple[int, int, int, int],
    ) -> float:
        region_area = float(max(1, (normalization_region[2] - normalization_region[0]) * (normalization_region[3] - normalization_region[1])))
        areas = [
            item.intersection_area(filter_region) / region_area
            for item in detections
            if item.class_name == class_name and item.intersects(filter_region)
        ]
        return max(areas, default=0.0)

    @staticmethod
    def _has_detection_in_region(
        detections: list[Detection],
        class_names: set[str],
        region: tuple[int, int, int, int],
    ) -> bool:
        return any(item.class_name in class_names and item.intersects(region) for item in detections)

    @staticmethod
    def _same_segment(left: FrameObservation, right: FrameObservation) -> bool:
        key_flags = ("muted_icon", "screen_share", "avatar_visible", "black_screen", "frozen_frame", "low_quality")
        return left.primary_state == right.primary_state and all(left.flags.get(flag) == right.flags.get(flag) for flag in key_flags)

    @staticmethod
    def _aggregate_flags(observations: list[FrameObservation]) -> dict[str, bool]:
        keys = observations[0].flags.keys()
        return {key: any(item.flags.get(key, False) for item in observations) for key in keys}

    @staticmethod
    def _deduplicate_reasons(reasons: list[str]) -> list[str]:
        seen: set[str] = set()
        output: list[str] = []
        for reason in reasons:
            if reason not in seen:
                seen.add(reason)
                output.append(reason)
        return output

    @staticmethod
    def _severity_ru_live(decision: str) -> str:
        if decision == "technical_issue":
            return "критично"
        if decision == "class_in_progress_with_issues":
            return "ошибка"
        if decision == "possible_problem":
            return "предупреждение"
        return "информация"

    @staticmethod
    def _summary_status_ru_live(has_problems: bool, final_decision: str) -> str:
        if not has_problems:
            if final_decision == "likely_finished":
                return "трансляция, вероятно, завершена"
            return "проблемы не обнаружены"
        if final_decision in {"class_in_progress", "likely_finished"}:
            return "во время трансляции были проблемы"
        return "обнаружены проблемы"

    @staticmethod
    def _true_flags_ru_live(flags: dict[str, bool]) -> list[str]:
        return [FLAG_TITLES_RU.get(key, key) for key, value in flags.items() if value]

    @staticmethod
    def _default_flags(**overrides: bool) -> dict[str, bool]:
        flags = {
            "teacher_in_main": False,
            "screen_share": False,
            "avatar_visible": False,
            "muted_icon": False,
            "empty_room": False,
            "black_screen": False,
            "frozen_frame": False,
            "low_quality": False,
            "window_not_found": False,
            "person_in_tile": False,
            "fullscreen_avatar": False,
        }
        flags.update(overrides)
        return flags


class _LiveJsonlWriter:
    def __init__(self, output_path: Path, only_on_problem: bool) -> None:
        self.output_path = output_path
        self.only_on_problem = only_on_problem
        self._handle = None
        self._seen_problem = False

    def write(self, event: dict[str, Any]) -> None:
        event_type = str(event.get("тип_события", ""))
        if event_type == "проблема_обнаружена":
            self._seen_problem = True

        if self.only_on_problem and not self._seen_problem:
            return

        if self._handle is None:
            self.output_path.parent.mkdir(parents=True, exist_ok=True)
            self._handle = self.output_path.open("w", encoding="utf-8")

        self._handle.write(json.dumps(event, ensure_ascii=False) + "\n")
        self._handle.flush()

    def close(self) -> None:
        if self._handle is not None:
            self._handle.close()
