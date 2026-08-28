import unittest

from discover import discover_from_toolify_html, find_official_url, normalize_queries, parse_candidates


class DiscoverTests(unittest.TestCase):
    def test_parse_candidates_keeps_manual_input(self):
        candidates = parse_candidates(["Runway|https://runwayml.com/|https://source.example|manual"])
        self.assertEqual(candidates[0].name, "Runway")
        self.assertEqual(candidates[0].url, "https://runwayml.com/")
        self.assertEqual(candidates[0].source_url, "https://source.example")
        self.assertEqual(candidates[0].source, "manual")

    def test_discover_from_toolify_html_extracts_ai_video_candidates(self):
        html = """
        <html><body>
          <a href="/tool/runway">Runway AI Video Generator</a>
          <a href="/tool/runway">Runway AI Video Generator</a>
          <a href="/tool/pika">Pika text to video</a>
          <a href="/tool/meeting-notes">Meeting Notes</a>
          <a href="/category/ai-video-generator">AI Video Generator</a>
        </body></html>
        """
        candidates = discover_from_toolify_html(html, "https://www.toolify.ai/search?q=ai+video", limit=10)
        self.assertEqual([c.name for c in candidates], ["Runway AI Video Generator", "Pika text to video"])
        self.assertEqual(candidates[0].url, "https://www.toolify.ai/tool/runway")
        self.assertEqual(candidates[0].source_url, "https://www.toolify.ai/search?q=ai+video")
        self.assertEqual(candidates[0].source, "toolify")

    def test_discover_from_toolify_html_applies_limit(self):
        html = """
        <a href="/tool/a">Alpha AI Video</a>
        <a href="/tool/b">Beta Image to Video</a>
        """
        candidates = discover_from_toolify_html(html, "https://www.toolify.ai/search?q=video", limit=1)
        self.assertEqual(len(candidates), 1)

    def test_discover_from_ai_video_context_keeps_product_name_only_links(self):
        html = """
        <a href="/tool/runway">Runway</a>
        <a href="/tool/pika">Pika</a>
        <a href="/tool/notion">Meeting Notes</a>
        """
        candidates = discover_from_toolify_html(html, "https://www.toolify.ai/search?q=ai+video+generator", limit=10)
        self.assertEqual([c.name for c in candidates], ["Runway", "Pika"])

    def test_find_official_url_prefers_external_product_site(self):
        html = """
        <a href="/tool/runway">Runway</a>
        <a href="https://twitter.com/runwayml">X</a>
        <a href="https://runwayml.com/?utm_source=toolify">Visit Website</a>
        """
        self.assertEqual(find_official_url(html, "https://www.toolify.ai/tool/runway"), "https://runwayml.com/?utm_source=toolify")

    def test_normalize_queries_uses_default_pool_for_empty_input(self):
        queries = normalize_queries([])
        self.assertGreater(len(queries), 3)
        self.assertIn("image to video ai", queries)
        self.assertIn("ai video ads", queries)

    def test_normalize_queries_dedupes_manual_queries(self):
        self.assertEqual(normalize_queries(["AI Video", " ai video ", "lip sync"]), ["AI Video", "lip sync"])


if __name__ == "__main__":
    unittest.main()
