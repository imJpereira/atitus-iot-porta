fetch("/api/health")
  .then((r) => r.json())
  .then((d) => (document.getElementById("status").textContent = `API: ${d.status}`))
  .catch(() => (document.getElementById("status").textContent = "API offline"));
