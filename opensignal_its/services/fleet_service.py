"""Helpers for fleet profile parsing and selected-device routing."""

from __future__ import annotations

from datetime import datetime
from ipaddress import ip_address
import json
from string import Template
from typing import Any, Awaitable, Callable

from ..models.device import DeviceConfig
from ..models.fleet import (
    FleetDeviceStatus,
    FleetRefreshView,
    FleetSnapshotEntry,
    RuntimeRegistryView,
)


class FleetService:
    DEFAULT_DEVICE_TYPE = "siemens_m60"
    MAP_SELECTION_STORAGE_KEY = "opensignal-map-selection"
    MAP_CREATE_STORAGE_KEY = "opensignal-map-create-controller"

    @staticmethod
    def _primary_profile_label(profile: dict[str, Any]) -> str:
        device_id = str(profile.get("device_id", "")).strip()
        return (
            str(profile.get("location_name", "")).strip()
            or str(profile.get("name", "")).strip()
            or device_id
        )

    @staticmethod
    def _coordinate_text(profile: dict[str, Any]) -> str:
        latitude = profile.get("latitude")
        longitude = profile.get("longitude")
        if latitude is None or longitude is None:
            return "Coordinates not set"
        return f"{float(latitude):.5f}, {float(longitude):.5f}"

    @staticmethod
    def _has_coordinates(profile: dict[str, Any]) -> bool:
        return profile.get("latitude") is not None and profile.get("longitude") is not None

    @staticmethod
    def _normalize_optional_coordinate(
        value: Any,
        label: str,
        *,
        min_value: float,
        max_value: float,
    ) -> float | None:
        if value is None:
            return None

        raw = str(value).strip()
        if not raw:
            return None

        try:
            number = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label} must be a number.") from exc

        if number < min_value or number > max_value:
            raise ValueError(f"{label} must be between {min_value} and {max_value}.")

        return number

    @staticmethod
    def _normalize_profile_item(item: dict[str, Any], label: str) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError(f"{label} must be an object.")

        device_id = str(item.get("device_id", "")).strip()
        ip_address = str(item.get("ip_address", "")).strip()
        latitude = FleetService._normalize_optional_coordinate(
            item.get("latitude"),
            f"{label} latitude",
            min_value=-90.0,
            max_value=90.0,
        )
        longitude = FleetService._normalize_optional_coordinate(
            item.get("longitude"),
            f"{label} longitude",
            min_value=-180.0,
            max_value=180.0,
        )
        if not device_id:
            raise ValueError(f"{label} is missing device_id (controller ID).")
        if not ip_address:
            raise ValueError(f"{label} is missing ip_address.")
        if (latitude is None) != (longitude is None):
            raise ValueError(f"{label} must define both latitude and longitude or leave both blank.")

        return {
            "device_id": device_id,
            "device_type": str(item.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)).strip()
            or FleetService.DEFAULT_DEVICE_TYPE,
            "ip_address": ip_address,
            "port": int(item.get("port", 161)),
            "community": str(item.get("community", "public")),
            "snmp_version": str(item.get("snmp_version", "auto")),
            "timeout_seconds": float(item.get("timeout_seconds", 3.0)),
            "retries": int(item.get("retries", 1)),
            "name": str(item.get("name", device_id)).strip() or device_id,
            "location_name": str(item.get("location_name", "")).strip(),
            "latitude": latitude,
            "longitude": longitude,
        }

    @staticmethod
    def parse_profiles_json(raw_json: str) -> list[dict[str, Any]]:
        raw = raw_json.strip()
        if not raw:
            return []
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError("Controller profiles JSON must be a list of profile objects.")

        profiles: list[dict[str, Any]] = []
        for idx, item in enumerate(payload, start=1):
            profiles.append(FleetService._normalize_profile_item(item, f"Controller profile #{idx}"))
        return profiles

    @staticmethod
    def normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
        return FleetService._normalize_profile_item(profile, "Controller profile")

    @staticmethod
    def build_profile_from_form(
        *,
        device_id: str,
        name: str,
        device_type: str,
        location_name: str = "",
        ip_address_text: str,
        port_text: str,
        community: str,
        snmp_version: str,
        timeout_text: str,
        retries_text: str,
        latitude_text: str = "",
        longitude_text: str = "",
    ) -> dict[str, Any]:
        try:
            port = int(port_text)
        except ValueError as exc:
            raise ValueError("Port must be an integer.") from exc
        if port < 1 or port > 65535:
            raise ValueError("Port must be between 1 and 65535.")

        try:
            timeout_seconds = float(timeout_text)
        except ValueError as exc:
            raise ValueError("Timeout must be a number.") from exc
        if timeout_seconds <= 0:
            raise ValueError("Timeout must be greater than 0.")

        try:
            retries = int(retries_text)
        except ValueError as exc:
            raise ValueError("Retries must be an integer.") from exc
        if retries < 0:
            raise ValueError("Retries cannot be negative.")

        raw_ip = ip_address_text.strip()
        try:
            normalized_ip = str(ip_address(raw_ip))
        except ValueError as exc:
            raise ValueError("IP address must be a valid IPv4 or IPv6 literal.") from exc

        latitude = FleetService._normalize_optional_coordinate(
            latitude_text,
            "Latitude",
            min_value=-90.0,
            max_value=90.0,
        )
        longitude = FleetService._normalize_optional_coordinate(
            longitude_text,
            "Longitude",
            min_value=-180.0,
            max_value=180.0,
        )
        if (latitude is None) != (longitude is None):
            raise ValueError("Latitude and longitude must both be provided or both be blank.")

        return FleetService.normalize_profile(
            {
                "device_id": device_id.strip(),
                "name": name.strip() or device_id.strip(),
                "location_name": location_name.strip(),
                "device_type": device_type.strip() or FleetService.DEFAULT_DEVICE_TYPE,
                "ip_address": normalized_ip,
                "port": port,
                "community": community.strip(),
                "snmp_version": snmp_version.strip(),
                "timeout_seconds": timeout_seconds,
                "retries": retries,
                "latitude": latitude,
                "longitude": longitude,
            }
        )

    @staticmethod
    def upsert_profile(
        profiles: list[dict[str, Any]],
        profile: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized = FleetService.normalize_profile(profile)
        updated = [dict(existing) for existing in profiles]
        for idx, existing in enumerate(updated):
            if str(existing.get("device_id", "")).strip() == normalized["device_id"]:
                updated[idx] = normalized
                break
        else:
            updated.append(normalized)
        return updated

    @staticmethod
    def remove_profile(
        profiles: list[dict[str, Any]],
        device_id: str,
    ) -> list[dict[str, Any]]:
        target = device_id.strip()
        return [
            dict(profile)
            for profile in profiles
            if str(profile.get("device_id", "")).strip() != target
        ]

    @staticmethod
    def dump_profiles_json(profiles: list[dict[str, Any]]) -> str:
        normalized = [FleetService.normalize_profile(profile) for profile in profiles]
        return json.dumps(normalized, indent=2)

    @staticmethod
    def format_profile_row(profile: dict[str, Any]) -> str:
        normalized = FleetService.normalize_profile(profile)
        name = str(normalized.get("name", normalized["device_id"])).strip()
        name_suffix = "" if name == normalized["device_id"] else f" | {name}"
        return (
            f"{normalized['device_id']} | {normalized['ip_address']}"
            f" | {normalized['device_type']}{name_suffix}"
        )

    @staticmethod
    def build_profile_rows(profiles: list[dict[str, Any]]) -> list[str]:
        return [FleetService.format_profile_row(profile) for profile in profiles]

    @staticmethod
    def build_profile_display_rows(
        profiles: list[dict[str, Any]],
        status_map: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            device_id = normalized["device_id"]
            status_payload = dict(status_map.get(device_id, {}))
            if "is_online" not in status_payload:
                status_label = "Unknown"
                status_scheme = "gray"
            elif bool(status_payload.get("is_online", False)):
                status_label = "Online"
                status_scheme = "green"
            else:
                status_label = "Offline"
                status_scheme = "red"

            has_coordinates = FleetService._has_coordinates(normalized)
            title = FleetService._primary_profile_label(normalized)
            subtitle = f"{device_id} | {normalized['ip_address']}"
            if title != device_id:
                subtitle = f"{subtitle} | {normalized['device_type']}"

            rows.append(
                {
                    "device_id": device_id,
                    "label": FleetService.format_profile_row(normalized),
                    "title": title,
                    "subtitle": subtitle,
                    "status_label": status_label,
                    "status_scheme": status_scheme,
                    "mapping_label": "Mapped" if has_coordinates else "Needs Coordinates",
                    "mapping_scheme": "blue" if has_coordinates else "amber",
                    "coordinate_text": FleetService._coordinate_text(normalized),
                    "detail_text": str(
                        status_payload.get(
                            "status_text",
                            "No poll data yet." if status_label == "Unknown" else "No status detail.",
                        )
                    ),
                    "updated_text": FleetService.format_status_timestamp(
                        str(status_payload.get("timestamp", ""))
                    ),
                }
            )
        return rows

    @staticmethod
    def format_status_timestamp(timestamp: str) -> str:
        raw = timestamp.strip()
        if not raw:
            return ""
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return f"Updated {parsed.isoformat(timespec='seconds').replace('T', ' ')}"
        except ValueError:
            return f"Updated {raw}"

    @staticmethod
    def filter_profiles(
        profiles: list[dict[str, Any]],
        query: str,
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip().lower()
        if not normalized_query:
            return [dict(profile) for profile in profiles]

        filtered: list[dict[str, Any]] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            haystack = " ".join(
                [
                    normalized["device_id"],
                    normalized["ip_address"],
                    normalized["device_type"],
                    str(normalized.get("name", "")),
                    str(normalized.get("location_name", "")),
                ]
            ).lower()
            if normalized_query in haystack:
                filtered.append(normalized)
        return filtered

    @staticmethod
    def filter_profiles_by_mapping(
        profiles: list[dict[str, Any]],
        mapping_filter: str,
    ) -> list[dict[str, Any]]:
        normalized_filter = mapping_filter.strip().lower()
        if normalized_filter not in {"mapped", "unmapped"}:
            return [FleetService.normalize_profile(profile) for profile in profiles]

        filtered: list[dict[str, Any]] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            has_coordinates = FleetService._has_coordinates(normalized)
            if normalized_filter == "mapped" and has_coordinates:
                filtered.append(normalized)
            elif normalized_filter == "unmapped" and not has_coordinates:
                filtered.append(normalized)
        return filtered

    @staticmethod
    def build_map_marker_rows(
        profiles: list[dict[str, Any]],
        status_map: dict[str, dict[str, Any]],
        selected_device_id: str,
    ) -> list[dict[str, Any]]:
        selected = selected_device_id.strip()
        markers: list[dict[str, Any]] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            latitude = normalized.get("latitude")
            longitude = normalized.get("longitude")
            if latitude is None or longitude is None:
                continue

            device_id = normalized["device_id"]
            status_payload = dict(status_map.get(device_id, {}))
            if "is_online" not in status_payload:
                status_label = "Unknown"
                marker_color = "#64748b"
            elif bool(status_payload.get("is_online", False)):
                status_label = "Online"
                marker_color = "#16a34a"
            else:
                status_label = "Offline"
                marker_color = "#dc2626"

            updated_text = FleetService.format_status_timestamp(
                str(status_payload.get("timestamp", ""))
            ) or "Awaiting refresh"
            detail_text = str(
                status_payload.get(
                    "status_text",
                    "No poll data yet." if status_label == "Unknown" else "No status detail.",
                )
            )
            label = (
                str(normalized.get("location_name", "")).strip()
                or str(normalized.get("name", "")).strip()
                or device_id
            )
            is_selected = device_id == selected

            markers.append(
                {
                    "device_id": device_id,
                    "label": label,
                    "subtitle": f"{device_id} | {normalized['ip_address']}",
                    "status_label": status_label,
                    "status_text": detail_text,
                    "updated_text": updated_text,
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                    "is_selected": is_selected,
                    "marker_color": "#4338ca" if is_selected else marker_color,
                    "marker_size": 18 if is_selected else 12,
                }
            )

        return markers

    @staticmethod
    def list_unmapped_profiles(profiles: list[dict[str, Any]]) -> list[str]:
        unmapped: list[str] = []
        for profile in profiles:
            normalized = FleetService.normalize_profile(profile)
            if not FleetService._has_coordinates(normalized):
                unmapped.append(normalized["device_id"])
        return unmapped

    @staticmethod
    def build_map_data(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not markers:
            return []

        return [
            {
                "type": "scattermapbox",
                "mode": "markers",
                "lat": [marker["latitude"] for marker in markers],
                "lon": [marker["longitude"] for marker in markers],
                "text": [marker["label"] for marker in markers],
                "customdata": [
                    [
                        marker["device_id"],
                        marker["status_text"],
                        marker["updated_text"],
                    ]
                    for marker in markers
                ],
                "marker": {
                    "size": [marker["marker_size"] for marker in markers],
                    "color": [marker["marker_color"] for marker in markers],
                    "opacity": 0.95,
                },
                "hovertemplate": (
                    "<b>%{text}</b><br>%{customdata[0]}"
                    "<br>%{customdata[1]}<br>%{customdata[2]}<extra></extra>"
                ),
            }
        ]

    @staticmethod
    def build_map_layout(markers: list[dict[str, Any]]) -> dict[str, Any]:
        center_lat, center_lon, zoom = FleetService._map_view(markers)

        return {
            "mapbox": {
                "style": "open-street-map",
                "center": {
                    "lat": center_lat,
                    "lon": center_lon,
                },
                "zoom": zoom,
            },
            "margin": {"l": 48, "r": 20, "t": 16, "b": 48},
            "paper_bgcolor": "rgba(0,0,0,0)",
            "plot_bgcolor": "rgba(255,255,255,0.72)",
            "showlegend": False,
            "hovermode": "closest",
            "clickmode": "event+select",
            "uirevision": "opensignal-controller-map",
        }

    @staticmethod
    def _map_view(markers: list[dict[str, Any]]) -> tuple[float, float, float]:
        if not markers:
            return 39.8283, -98.5795, 4.0

        latitudes = [float(marker["latitude"]) for marker in markers]
        longitudes = [float(marker["longitude"]) for marker in markers]
        center_lat = sum(latitudes) / len(latitudes)
        center_lon = sum(longitudes) / len(longitudes)
        if len(markers) == 1:
            zoom = 13.0
        elif len(markers) <= 4:
            zoom = 10.0
        else:
            zoom = 8.0
        return center_lat, center_lon, zoom

    @staticmethod
    def build_map_src_doc(
        markers: list[dict[str, Any]],
        selected_device_id: str = "",
    ) -> str:
        center_lat, center_lon, zoom = FleetService._map_view(markers)
        meta = {
            "storageKey": FleetService.MAP_SELECTION_STORAGE_KEY,
            "creationStorageKey": FleetService.MAP_CREATE_STORAGE_KEY,
            "selectedDeviceId": str(selected_device_id).strip(),
            "defaultLat": center_lat,
            "defaultLon": center_lon,
            "defaultZoom": zoom,
        }
        markers_json = json.dumps(markers, ensure_ascii=False).replace("<", "\\u003c")
        meta_json = json.dumps(meta, ensure_ascii=False).replace("<", "\\u003c")

        return Template(
            """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        html, body {
            margin: 0;
            width: 100%;
            height: 100%;
            overflow: hidden;
            background: #eef2ff;
            font-family: Inter, ui-sans-serif, system-ui, sans-serif;
        }
        #map {
            width: 100%;
            height: 100%;
        }
        .leaflet-container {
            background: #eef2ff;
        }
        .map-popup {
            font-size: 12px;
            line-height: 1.4;
        }
        .map-popup strong {
            display: block;
            font-size: 13px;
            margin-bottom: 4px;
        }
        .selection-pin {
            background: transparent;
            border: none;
        }
        .selection-pin__outer {
            display: block;
            width: 20px;
            height: 20px;
            background: linear-gradient(180deg, #fbbf24 0%, #f59e0b 100%);
            border: 3px solid #ffffff;
            border-radius: 50% 50% 50% 0;
            transform: rotate(-45deg);
            box-shadow: 0 10px 18px rgba(15, 23, 42, 0.24);
            position: relative;
        }
        .selection-pin__inner {
            position: absolute;
            inset: 4px;
            border-radius: 50%;
            background: rgba(255, 255, 255, 0.92);
        }
    </style>
</head>
<body>
    <div id="map"></div>
    <script id="map-meta" type="application/json">$meta_json</script>
    <script id="map-data" type="application/json">$markers_json</script>
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        (function () {
            const escapeHtml = (value) => String(value).replace(/[&<>\"']/g, (character) => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                '\"': '&quot;',
                "'": '&#39;',
            }[character]));

            const mapMeta = JSON.parse(document.getElementById('map-meta').textContent || '{}');
            const markers = JSON.parse(document.getElementById('map-data').textContent || '[]');
            const storageKey = mapMeta.storageKey || 'opensignal-map-selection';
            const creationStorageKey = mapMeta.creationStorageKey || 'opensignal-map-create-controller';
            const selectedDeviceId = mapMeta.selectedDeviceId || '';
            const defaultLat = Number.isFinite(mapMeta.defaultLat) ? mapMeta.defaultLat : 39.8283;
            const defaultLon = Number.isFinite(mapMeta.defaultLon) ? mapMeta.defaultLon : -98.5795;
            const defaultZoom = Number.isFinite(mapMeta.defaultZoom) ? mapMeta.defaultZoom : 4;

            const selectionIcon = L.divIcon({
                className: 'selection-pin',
                html: '<span class="selection-pin__outer"><span class="selection-pin__inner"></span></span>',
                iconSize: [24, 24],
                iconAnchor: [12, 22],
                popupAnchor: [0, -22],
            });

            let selectionMarker = null;

            const writeStorageEvent = (key, value) => {
                try {
                    const previousValue = window.parent.localStorage.getItem(key);
                    window.parent.localStorage.setItem(key, value);
                    window.parent.dispatchEvent(new StorageEvent('storage', {
                        key,
                        oldValue: previousValue,
                        newValue: value,
                        url: window.location.href,
                        storageArea: window.parent.localStorage,
                    }));
                } catch (error) {
                    try {
                        localStorage.setItem(key, value);
                    } catch (ignored) {
                        // The parent storage bridge is best-effort.
                    }
                }
            };

            const map = L.map('map', {
                zoomControl: true,
                scrollWheelZoom: true,
                doubleClickZoom: true,
            });
            window.__opensignalMap = map;

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '&copy; OpenStreetMap contributors',
            }).addTo(map);

            const setSelectionPoint = (latitude, longitude, shouldBroadcast = true) => {
                const nextLatitude = Number(latitude);
                const nextLongitude = Number(longitude);
                if (!Number.isFinite(nextLatitude) || !Number.isFinite(nextLongitude)) {
                    return;
                }

                const payload = JSON.stringify({
                    latitude: nextLatitude,
                    longitude: nextLongitude,
                    source: 'map-point',
                    timestamp: Date.now(),
                });

                if (!selectionMarker) {
                    selectionMarker = L.marker([nextLatitude, nextLongitude], {
                        draggable: true,
                        icon: selectionIcon,
                        autoPan: true,
                        bubblingMouseEvents: false,
                        riseOnHover: true,
                        zIndexOffset: 1000,
                    }).addTo(map);

                    selectionMarker.on('dragend', (event) => {
                        const latlng = event.target.getLatLng();
                        setSelectionPoint(latlng.lat, latlng.lng, true);
                    });
                } else {
                    selectionMarker.setLatLng([nextLatitude, nextLongitude]);
                }

                if (shouldBroadcast) {
                    writeStorageEvent(creationStorageKey, payload);
                }
            };

            const restoreSelectionPoint = () => {
                try {
                    const rawSelection = window.parent.localStorage.getItem(creationStorageKey) || localStorage.getItem(creationStorageKey);
                    if (!rawSelection) {
                        return;
                    }

                    const selection = JSON.parse(rawSelection);
                    if (!selection || selection.latitude === undefined || selection.longitude === undefined) {
                        return;
                    }

                    setSelectionPoint(selection.latitude, selection.longitude, true);
                } catch (error) {
                    // The selection pin is best-effort.
                }
            };

            const bounds = [];

            markers.forEach((marker) => {
                const isSelected = marker.device_id === selectedDeviceId;
                const color = isSelected ? '#4f46e5' : (marker.marker_color || '#2563eb');
                const radius = isSelected ? 10 : (marker.marker_size || 8);
                const circle = L.circleMarker([marker.latitude, marker.longitude], {
                    radius,
                    color,
                    fillColor: color,
                    fillOpacity: 0.9,
                    weight: isSelected ? 3 : 2,
                    bubblingMouseEvents: false,
                }).addTo(map);

                circle.bindTooltip(escapeHtml(marker.label), { direction: 'top', opacity: 0.95 });
                circle.bindPopup(
                    '<div class="map-popup">' +
                    '<strong>' + escapeHtml(marker.label) + '</strong>' +
                    '<div>' + escapeHtml(marker.device_id) + '</div>' +
                    '<div>' + escapeHtml(marker.status_text) + '</div>' +
                    '<div>' + escapeHtml(marker.updated_text) + '</div>' +
                    '</div>'
                );
                circle.on('click', () => {
                    const payload = marker.device_id + '::' + Date.now();
                    writeStorageEvent(storageKey, payload);
                });
                bounds.push([marker.latitude, marker.longitude]);
            });

            restoreSelectionPoint();

            if (selectionMarker) {
                const selectedLatLng = selectionMarker.getLatLng();
                bounds.push([selectedLatLng.lat, selectedLatLng.lng]);
            }

            map.on('click', (event) => {
                setSelectionPoint(event.latlng.lat, event.latlng.lng, true);
            });

            if (bounds.length === 1) {
                map.setView(bounds[0], 13);
            } else if (bounds.length > 1) {
                map.fitBounds(bounds, { padding: [32, 32] });
            } else {
                map.setView([defaultLat, defaultLon], defaultZoom);
            }

            requestAnimationFrame(() => map.invalidateSize());
        }());
    </script>
</body>
</html>
"""
        ).substitute(meta_json=meta_json, markers_json=markers_json)

    @staticmethod
    def sort_profiles(
        profiles: list[dict[str, Any]],
        sort_key: str,
        descending: bool = False,
    ) -> list[dict[str, Any]]:
        normalized_profiles = [FleetService.normalize_profile(profile) for profile in profiles]
        normalized_key = sort_key.strip().lower()

        def _sort_value(profile: dict[str, Any]):
            if normalized_key == "name":
                return str(profile.get("name", "")).strip().lower(), profile["device_id"].lower()
            if normalized_key == "location_name":
                return (
                    str(profile.get("location_name", "")).strip().lower(),
                    str(profile.get("name", "")).strip().lower(),
                    profile["device_id"].lower(),
                )
            if normalized_key == "ip_address":
                return ip_address(str(profile["ip_address"])), profile["device_id"].lower()
            if normalized_key == "device_type":
                return str(profile.get("device_type", "")).strip().lower(), profile["device_id"].lower()
            return profile["device_id"].lower(), str(profile.get("name", "")).strip().lower()

        return sorted(normalized_profiles, key=_sort_value, reverse=descending)

    @staticmethod
    def build_device_config(profile: dict[str, Any]) -> DeviceConfig:
        return DeviceConfig(
            ip_address=str(profile["ip_address"]),
            port=int(profile.get("port", 161)),
            name=str(profile.get("name", profile.get("device_id", "Device"))),
            community=str(profile.get("community", "public")),
            snmp_version=str(profile.get("snmp_version", "auto")),
            timeout_seconds=float(profile.get("timeout_seconds", 3.0)),
            retries=int(profile.get("retries", 1)),
        )

    @staticmethod
    def select_profile(
        profiles: list[dict[str, Any]],
        selected_device_id: str,
    ) -> dict[str, Any] | None:
        if not profiles:
            return None
        target = selected_device_id.strip()
        if target:
            for profile in profiles:
                if str(profile.get("device_id", "")).strip() == target:
                    return profile
        return profiles[0]

    @staticmethod
    def resolve_target(
        profiles: list[dict[str, Any]],
        selected_device_id: str,
        fallback_config: DeviceConfig,
        fallback_device_id: str = "single-device",
        fallback_device_type: str = DEFAULT_DEVICE_TYPE,
    ) -> tuple[str, str, DeviceConfig]:
        selected = FleetService.select_profile(profiles, selected_device_id)
        if selected is None:
            return (
                fallback_device_type,
                fallback_device_id.strip() or "single-device",
                fallback_config,
            )

        config = FleetService.build_device_config(selected)
        return (
            str(selected.get("device_type", FleetService.DEFAULT_DEVICE_TYPE)),
            str(selected.get("device_id", config.name)),
            config,
        )

    @staticmethod
    def summarize_status_map(status_map: dict[str, dict[str, Any]]) -> dict[str, int]:
        total = len(status_map)
        online = sum(1 for payload in status_map.values() if bool(payload.get("is_online", False)))
        offline = max(0, total - online)
        return {
            "total": total,
            "online": online,
            "offline": offline,
        }

    @staticmethod
    def format_status_row(device_id: str, device_type: str, payload: dict[str, Any]) -> str:
        is_online = bool(payload.get("is_online", False))
        status_text = str(payload.get("status_text", "unknown"))
        return f"{device_id} [{device_type}] {'ONLINE' if is_online else 'OFFLINE'} - {status_text}"

    @staticmethod
    def build_snapshot_entry(
        device_id: str,
        device_type: str,
        payload: dict[str, Any] | None,
        mp_model: int,
        error: str = "",
    ) -> FleetSnapshotEntry:
        if error:
            status_payload = FleetDeviceStatus(
                device_type=device_type,
                is_online=False,
                status_text=f"error: {error}",
                timestamp="",
            )
            row = f"{device_id} [{device_type}] ERROR - {error}"
            return FleetSnapshotEntry(
                device_id=device_id,
                device_type=device_type,
                status=status_payload,
                row=row,
                payload=None,
                mp_model=int(mp_model),
            )

        safe_payload = dict(payload or {})
        status_payload = FleetDeviceStatus(
            device_type=device_type,
            is_online=bool(safe_payload.get("is_online", False)),
            status_text=str(safe_payload.get("status_text", "unknown")),
            timestamp=str(safe_payload.get("timestamp", "")),
        )
        return FleetSnapshotEntry(
            device_id=device_id,
            device_type=device_type,
            status=status_payload,
            row=FleetService.format_status_row(device_id, device_type, safe_payload),
            payload=safe_payload,
            mp_model=int(mp_model),
        )

    @staticmethod
    def compile_refresh_view(
        entries: list[FleetSnapshotEntry],
        selected_device_id: str,
    ) -> FleetRefreshView:
        rows: list[str] = []
        status_by_id: dict[str, FleetDeviceStatus] = {}
        selected_payload: dict[str, Any] | None = None
        selected_mp_model = 1
        selected_device_type = FleetService.DEFAULT_DEVICE_TYPE

        for entry in entries:
            device_id = str(entry.device_id)
            rows.append(str(entry.row))
            status_by_id[device_id] = entry.status
            if device_id != selected_device_id:
                continue
            payload = entry.payload
            if isinstance(payload, dict):
                selected_payload = dict(payload)
                selected_mp_model = int(entry.mp_model)
                selected_device_type = str(entry.device_type or FleetService.DEFAULT_DEVICE_TYPE)

        return FleetRefreshView(
            rows=rows,
            status_by_id=status_by_id,
            selected_payload=selected_payload,
            selected_mp_model=selected_mp_model,
            selected_device_type=selected_device_type,
            selected_device_id=selected_device_id,
        )

    @staticmethod
    async def collect_refresh_view(
        profiles: list[dict[str, Any]],
        selected_device_id: str,
        collector: Callable[..., Awaitable[tuple[dict[str, Any], int]]],
    ) -> FleetRefreshView:
        selected = FleetService.select_profile(profiles, selected_device_id)
        effective_selected_id = str(selected.get("device_id", "")).strip() if selected is not None else ""

        entries: list[FleetSnapshotEntry] = []
        for profile in profiles:
            device_id = str(profile.get("device_id", "unknown"))
            device_type = str(profile.get("device_type", FleetService.DEFAULT_DEVICE_TYPE))
            config = FleetService.build_device_config(profile)
            try:
                payload, mp_model = await collector(device_type, config, device_id=device_id)
                entries.append(
                    FleetService.build_snapshot_entry(
                        device_id=device_id,
                        device_type=device_type,
                        payload=payload,
                        mp_model=mp_model,
                    )
                )
            except Exception as exc:
                entries.append(
                    FleetService.build_snapshot_entry(
                        device_id=device_id,
                        device_type=device_type,
                        payload=None,
                        mp_model=1,
                        error=str(exc),
                    )
                )

        view = FleetService.compile_refresh_view(entries, effective_selected_id)
        view.selected_device_id = effective_selected_id
        return view

    @staticmethod
    def build_runtime_registry_view(status: dict[str, Any]) -> RuntimeRegistryView:
        count = int(status.get("count", 0) or 0)
        running_count = int(status.get("running_count", 0) or 0)
        keys = [str(key) for key in status.get("keys", [])]
        running_keys = {str(key) for key in status.get("running_keys", [])}
        rows = [
            f"{key}{' (polling)' if key in running_keys else ''}"
            for key in keys
        ]
        return RuntimeRegistryView(
            summary=f"Active poll sessions: {count} sites, {running_count} polling loops running.",
            rows=rows,
            count=count,
            running_count=running_count,
        )
