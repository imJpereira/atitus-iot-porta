// Redirect to login on any 401 response
async function apiFetch(url, opts) {
  const res = await fetch(url, opts);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("not authenticated");
  }
  return res;
}

// Logout handler
document.addEventListener("click", async (e) => {
  if (e.target.id === "btn-logout") {
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }
});

apiFetch("/api/health")
  .then((r) => r.json())
  .then((d) => (document.getElementById("status").textContent = `API: ${d.status}`))
  .catch(() => (document.getElementById("status").textContent = "API offline"));
