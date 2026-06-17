"""Amazon Photos Client - A clean-room implementation of the Amazon Photos undocumented API."""

import logging
import random
import time
from typing import Any, Dict, Generator, List

from curl_cffi import requests as curl_req

from amazon_photos_mcp.errors import AuthenticationError, RateLimitError

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.3",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1.2 Safari/605.1.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.1.2 Safari/605.1.1",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.3",
]


class AmazonPhotosClient:
    def __init__(self, cookies: dict[str, str]):
        self.tld = self._determine_tld(cookies)
        self.drive_url = f"https://www.amazon.{self.tld}/drive/v1"
        self.base_params: dict[str, Any] = {
            "asset": "ALL",
            "tempLink": "false",
            "resourceVersion": "V2",
            "ContentType": "JSON",
        }

        session_id = cookies.get("session-id", "")

        # Configure curl_cffi session with browser impersonation
        self.client = curl_req.Session()
        self.client.headers.update({
            "user-agent": random.choice(USER_AGENTS),
            "x-amzn-sessionid": session_id,
        })
        if cookies:
            self.client.cookies.update(cookies)
        self._cookies = cookies
        self._root_node: dict[str, Any] | None = None

    def _determine_tld(self, cookies: dict[str, str]) -> str:
        if "ubid-acbca" in cookies or "at-acbca" in cookies:
            return "ca"
        elif "ubid-acbuk" in cookies or "at-acbuk" in cookies:
            return "co.uk"
        elif "ubid-acbde" in cookies or "at-acbde" in cookies:
            return "de"
        elif "ubid-acbfr" in cookies or "at-acbfr" in cookies:
            return "fr"
        elif "ubid-acbit" in cookies or "at-acbit" in cookies:
            return "it"
        elif "ubid-acbes" in cookies or "at-acbes" in cookies:
            return "es"
        return "com"

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Centralized request handler with error wrapping and retry."""
        kwargs.setdefault("timeout", 30.0)
        max_retries = 3
        last_exception: Exception | None = None

        for attempt in range(max_retries):
            try:
                resp = self.client.request(method, url, **kwargs)
            except curl_req.RequestsError as e:
                last_exception = e
                if attempt < max_retries - 1:
                    delay = 0.5 * (2**attempt) + random.uniform(0, 0.5)
                    time.sleep(delay)
                    continue
                raise Exception(f"Request failed after {max_retries} attempts: {e}") from e

            if resp.status_code == 401:
                raise AuthenticationError("Authentication failed. Cookies may be expired.")
            if resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                if attempt < max_retries - 1:
                    time.sleep(min(retry_after, 5))
                    continue
                raise RateLimitError(retry_after=retry_after)
            if resp.status_code == 503:
                if attempt < max_retries - 1:
                    time.sleep(min(2**attempt, 5))
                    continue
                raise RateLimitError(retry_after=30)

            resp.raise_for_status()
            return resp

        raise Exception(f"Request failed after {max_retries} attempts") from last_exception

    def usage(self) -> Dict[str, Any]:
        """Get account usage stats."""
        resp = self.request("GET", f"{self.drive_url}/account/usage", params=self.base_params)
        return resp.json()  # type: ignore[no-any-return]

    def get_root(self) -> Dict[str, Any]:
        """Get the root node for the account to find the ownerId."""
        if self._root_node:
            return self._root_node

        params = {"filters": "isRoot:true"} | self.base_params
        resp = self.request("GET", f"{self.drive_url}/nodes", params=params)
        data = resp.json().get("data", [])
        if data:
            self._root_node = data[0]
            return self._root_node
        return {}

    def get_file(self, node_id: str) -> Dict[str, Any]:
        """Get metadata for a specific node."""
        resp = self.request("GET", f"{self.drive_url}/nodes/{node_id}", params=self.base_params)
        return resp.json()  # type: ignore[no-any-return]

    def query(
        self,
        filters: str = "type:(PHOTOS OR VIDEOS)",
        offset: int = 0,
        limit: float = float("inf"),
        sort: str = "['createdDate DESC']",
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """Search media with filters and automatically paginate to return all matching results."""
        results: list[dict[str, Any]] = []
        current_offset = offset
        page_limit = 200

        while True:
            params = self.base_params | {
                "limit": min(limit - len(results), page_limit) if limit != float("inf") else page_limit,
                "offset": current_offset,
                "filters": filters,
                "lowResThumbnail": "true",
                "searchContext": "customer",
                "sort": sort,
            }
            resp = self.request("GET", f"{self.drive_url}/search", params=params)
            data = resp.json()

            items = data.get("data", [])
            results.extend(items)

            # If we've hit our requested limit or the API returned fewer items than requested (end of data)
            if len(results) >= limit or len(items) < params["limit"]:
                break

            current_offset += len(items)

        return results

    def photos(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return self.query("type:(PHOTOS)", **kwargs)

    def videos(self, **kwargs: Any) -> List[Dict[str, Any]]:
        return self.query("type:(VIDEOS)", **kwargs)

    def trash(self, node_ids: List[str], filters: str = "") -> List[Dict[str, Any]]:
        """Move nodes to trash."""
        results = []
        # Batch max size is 50
        for i in range(0, len(node_ids), 50):
            batch = node_ids[i : i + 50]
            resp = self.request(
                "PATCH",
                f"{self.drive_url}/trash",
                json={
                    "recurse": "true",
                    "op": "add",
                    "filters": filters,
                    "conflictResolution": "RENAME",
                    "value": batch,
                    "resourceVersion": "V2",
                    "ContentType": "JSON",
                },
            )
            results.append(resp.json())
        return results

    def restore(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Restore nodes from trash."""
        results = []
        for i in range(0, len(node_ids), 50):
            batch = node_ids[i : i + 50]
            resp = self.request(
                "PATCH",
                f"{self.drive_url}/trash",
                json={
                    "recurse": "true",
                    "op": "remove",
                    "conflictResolution": "RENAME",
                    "value": batch,
                    "resourceVersion": "V2",
                    "ContentType": "JSON",
                },
            )
            results.append(resp.json())
        return results

    def favorite(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Add media to favorites."""
        results = []
        for nid in node_ids:
            resp = self.request(
                "PATCH",
                f"{self.drive_url}/nodes/{nid}",
                json={"settings": {"favorite": True}, "resourceVersion": "V2", "ContentType": "JSON"},
            )
            results.append(resp.json())
        return results

    def unfavorite(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Remove media from favorites."""
        results = []
        for nid in node_ids:
            resp = self.request(
                "PATCH",
                f"{self.drive_url}/nodes/{nid}",
                json={"settings": {"favorite": False}, "resourceVersion": "V2", "ContentType": "JSON"},
            )
            results.append(resp.json())
        return results

    def hide(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Hide media."""
        results = []
        for nid in node_ids:
            resp = self.request(
                "PATCH",
                f"{self.drive_url}/nodes/{nid}",
                json={"settings": {"hidden": True}, "resourceVersion": "V2", "ContentType": "JSON"},
            )
            results.append(resp.json())
        return results

    def unhide(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Unhide media."""
        results = []
        for nid in node_ids:
            resp = self.request(
                "PATCH",
                f"{self.drive_url}/nodes/{nid}",
                json={"settings": {"hidden": False}, "resourceVersion": "V2", "ContentType": "JSON"},
            )
            results.append(resp.json())
        return results

    def get_folders(self) -> List[Dict[str, Any]]:
        """Get all folders in Amazon Photos."""
        # Simple iterative folder fetcher instead of full recursive tree
        folders = []
        offset = 0
        limit = 200
        while True:
            params = self.base_params | {"limit": limit, "offset": offset, "filters": "kind:(FOLDER)"}
            resp = self.request("GET", f"{self.drive_url}/search", params=params)
            data = resp.json().get("data", [])
            folders.extend(data)
            if len(data) < limit:
                break
            offset += limit
        return folders

    def albums(self) -> List[Dict[str, Any]]:
        """Get all albums."""
        resp = self.request(
            "GET", f"{self.drive_url}/nodes", params={"filters": "kind:(VISUAL_COLLECTION)"} | self.base_params
        )
        return resp.json().get("data", [])  # type: ignore[no-any-return]

    def create_album(self, album_name: str, node_ids: list[str] | None = None) -> Dict[str, Any]:
        """Create a new album."""
        resp = self.request(
            "POST",
            f"{self.drive_url}/nodes",
            json={"kind": "VISUAL_COLLECTION", "name": album_name, "resourceVersion": "V2", "ContentType": "JSON"},
        )
        album = resp.json()
        if node_ids:
            self.add_to_album(album["id"], node_ids)
        return album  # type: ignore[no-any-return]

    def add_to_album(self, album_id: str, node_ids: List[str]) -> Dict[str, Any]:
        """Add media to an album."""
        resp = self.request(
            "PATCH",
            f"{self.drive_url}/nodes/{album_id}/children",
            json={"op": "add", "value": node_ids, "resourceVersion": "V2", "ContentType": "JSON"},
        )
        return resp.json()  # type: ignore[no-any-return]

    def remove_from_album(self, album_id: str, node_ids: List[str]) -> Dict[str, Any]:
        """Remove media from an album."""
        resp = self.request(
            "PATCH",
            f"{self.drive_url}/nodes/{album_id}/children",
            json={"op": "remove", "value": node_ids, "resourceVersion": "V2", "ContentType": "JSON"},
        )
        return resp.json()  # type: ignore[no-any-return]

    def aggregations(self, category: str) -> List[Dict[str, Any]]:
        """Get aggregations (e.g., allPeople, things, locations).

        Returns a list of aggregation entries for the given category.
        """
        resp = self.request(
            "GET",
            f"{self.drive_url}/search/aggregation",
            params={"aggregationContext": "all", "category": category, "resourceVersion": "V2", "ContentType": "JSON"},
        )
        return resp.json().get("aggregations", {}).get(category, [])  # type: ignore[no-any-return]

    def update_cluster_name(self, cluster_id: str, name: str) -> Dict[str, Any]:
        """Update the name of a person cluster."""
        resp = self.request(
            "PUT",
            f"{self.drive_url}/cluster/name",
            json={"sourceCluster": cluster_id, "newName": name, "context": "all", "ContentType": "JSON"},
        )
        return resp.json()  # type: ignore[no-any-return]

    def merge_clusters(self, target_cluster_id: str, source_cluster_ids: List[str]) -> Dict[str, Any]:
        """Merge multiple person clusters into one."""
        resp = self.request(
            "POST",
            f"{self.drive_url}/cluster/merge",
            json={
                "sourceClusters": source_cluster_ids,
                "targetCluster": target_cluster_id,
                "context": "all",
                "ContentType": "JSON",
            },
        )
        return resp.json()  # type: ignore[no-any-return]

    def download_stream(self, node_id: str) -> Generator[bytes, None, None]:
        """Yields bytes for downloading a node. Generator function."""
        root = self.get_root()
        owner_id = root.get("ownerId", "")
        params = {"querySuffix": "?download=true", "ownerId": owner_id}
        url = f"{self.drive_url}/nodes/{node_id}/contentRedirection"

        try:
            with self.client.stream("GET", url, params=params) as resp:
                resp.raise_for_status()
                yielded = False
                for chunk in resp.iter_content(chunk_size=8192):
                    yielded = True
                    yield chunk
                if not yielded:
                    logger.warning("download_stream for %s returned empty response body", node_id)
        except curl_req.RequestsError as e:
            logger.error("download_stream error for %s: %s", node_id, e)
            raise

    def trashed(self) -> List[Dict[str, Any]]:
        """List items in the trash."""
        params = self.base_params | {
            "filters": "isTrashed:true",
            "limit": 200,
            "offset": 0,
            "lowResThumbnail": "true",
            "sort": "['modifiedDate DESC']",
        }
        resp = self.request("GET", f"{self.drive_url}/search", params=params)
        return resp.json().get("data", [])  # type: ignore[no-any-return]

    def delete(self, node_ids: List[str]) -> List[Dict[str, Any]]:
        """Permanently delete items (bypasses trash).

        Uses the trash endpoint with permanent deletion semantics.
        """
        results = []
        for nid in node_ids:
            resp = self.request("DELETE", f"{self.drive_url}/nodes/{nid}", params=self.base_params)
            results.append(resp.json())
        return results

    def upload(self, path: str) -> List[Dict[str, Any]]:
        """Upload files from a local directory or file path to Amazon Photos.

        Args:
            path: Path to a file or directory to upload

        Returns:
            List of upload results
        """
        import mimetypes
        from pathlib import Path as _Path

        p = _Path(path)
        files_to_upload = [f for f in p.rglob("*") if f.is_file()] if p.is_dir() else [p]

        results = []
        for file_path in files_to_upload:
            try:
                content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
                file_size = file_path.stat().st_size

                upload_url = f"{self.drive_url}/upload/init"
                init_resp = self.request(
                    "POST",
                    upload_url,
                    json={
                        "name": file_path.name,
                        "contentType": content_type,
                        "contentLength": file_size,
                        "resourceVersion": "V2",
                        "ContentType": "JSON",
                    },
                )
                upload_info = init_resp.json()

                upload_url = upload_info.get("uploadUrl") or upload_info.get("url")
                if upload_url:
                    with open(str(file_path), "rb") as f:
                        data = f.read()
                    upload_resp = self.client.put(upload_url, data=data)
                    upload_resp.raise_for_status()

                results.append({"name": file_path.name, "status": "ok"})
            except Exception as e:
                results.append({"name": file_path.name, "status": "error", "error": str(e)})

        return results

    def download(self, node_ids: List[str], out: str) -> List[Dict[str, Any]]:
        """Download files by node ID to a local directory.

        Args:
            node_ids: List of node IDs to download
            out: Output directory path

        Returns:
            List of dicts with download results for each file
        """
        from pathlib import Path as _Path

        results = []
        out_path = _Path(out)
        out_path.mkdir(parents=True, exist_ok=True)

        for nid in node_ids:
            try:
                node = self.get_file(nid)
                name = node.get("name", nid)
                dest = out_path / name

                with open(str(dest), "wb") as f:
                    for chunk in self.download_stream(nid):
                        f.write(chunk)

                results.append({"node_id": nid, "name": name, "status": "ok", "path": str(dest)})
            except Exception as e:
                results.append({"node_id": nid, "status": "error", "error": str(e)})

        return results
