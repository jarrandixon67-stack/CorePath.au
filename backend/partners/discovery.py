"""Bounded OpenStreetMap candidate discovery; discovery never establishes consent."""

import json

import httpx

from partners.models import BusinessSeed, public_url


class DiscoveryUnavailable(Exception):
    pass


def discover(request, *, client=None):
    box = ",".join(str(v) for v in request.bbox)
    query = (
        f'[out:json][timeout:20];(nwr["healthcare"]({box});'
        f'nwr["amenity"~"^(clinic|doctors|dentist|hospital|pharmacy)$"]({box});'
        f'nwr["leisure"~"^(fitness_centre|fitness_station|sports_centre)$"]({box});'
        f'nwr["shop"~"^(chemist|nutrition_supplements|health_food)$"]({box}););'
        f"out tags center {request.limit};"
    )

    def fetch(connection):
        # Fixed origin and bounded response: no caller-controlled URL fetching.
        with connection.stream(
            "POST",
            "https://overpass-api.de/api/interpreter",
            data={"data": query},
            headers={"User-Agent": "CorePath-Partner-Research/0.1"},
        ) as response:
            response.raise_for_status()
            data = bytearray()
            for chunk in response.iter_bytes():
                data.extend(chunk)
                if len(data) > 2_000_000:
                    raise DiscoveryUnavailable("Directory response exceeded the batch limit")
        return json.loads(data)

    try:
        if client:
            result = fetch(client)
        else:
            with httpx.Client(timeout=30, follow_redirects=False) as connection:
                result = fetch(connection)
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("elements"), list)
            or result.get("remark")
        ):
            raise DiscoveryUnavailable("Directory returned an incomplete search")
        businesses = []
        for element in result["elements"][: request.limit]:
            if not isinstance(element, dict):
                continue
            tags = element.get("tags", {})
            if not isinstance(tags, dict) or not isinstance(tags.get("name"), str):
                continue
            if not isinstance(tags.get("addr:country", request.country), str):
                continue
            if (
                not tags.get("name")
                or element.get("type") not in ("node", "way", "relation")
                or type(element.get("id")) is not int
            ):
                continue
            # The country is the operator's requested search area, not registry verification.
            # A conflicting explicit country tag is excluded; untagged records remain candidates.
            if tags.get("addr:country", request.country).upper() != request.country:
                continue
            website = tags.get("website") or tags.get("contact:website")
            if not isinstance(website, str):
                website = None
            try:
                website = public_url(website) if website else None
            except ValueError:
                website = None
            health = (
                "healthcare" in tags
                or tags.get("amenity") in {"clinic", "doctors", "dentist", "hospital", "pharmacy"}
                or tags.get("leisure") in {"fitness_centre", "fitness_station", "sports_centre"}
                or tags.get("shop") in {"chemist", "nutrition_supplements", "health_food"}
            )
            if not health:
                continue
            category = next(
                (
                    tags[k]
                    for k in (
                        "shop",
                        "office",
                        "craft",
                        "healthcare",
                        "amenity",
                        "tourism",
                        "leisure",
                    )
                    if k in tags
                ),
                "unclassified",
            )
            try:
                businesses.append(
                    BusinessSeed(
                        name=tags["name"],
                        country=request.country,
                        category=category,
                        locality=tags.get("addr:city", ""),
                        sector=request.sector,
                        website=website,
                        source_url=f"https://www.openstreetmap.org/{element['type']}/{element['id']}",
                        attribution="© OpenStreetMap contributors, ODbL; country from requested search area",
                    )
                )
            except ValueError:
                continue
        return businesses
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise DiscoveryUnavailable(
            "Business discovery is unavailable; retry a smaller batch later"
        ) from exc
