let events = [];
let current = 0;

function showEvent(idx) {
  if (events.length === 0) {
    document.getElementById("eventBox").innerHTML = "<p>No events found.</p>";
    return;
  }
  const e = events[idx];
  const date = e.date || e.start_date || "N/A";
  const time = e.time ||
    ((e.start_time ? e.start_time : "") +
     (e.end_time ? " - " + e.end_time : "")) || "N/A";
  const location = e.location || "N/A";
  const description = e.description
    ? (e.description.startsWith("http")
        ? `<a href="${e.description}" target="_blank">${e.description}</a>`
        : e.description)
    : "N/A";

  document.getElementById("eventBox").innerHTML = `
    <h2>${e.title || "Untitled Event"}</h2>
    <p><strong>Date:</strong> ${date}</p>
    <p><strong>Time:</strong> ${time}</p>
    <p><strong>Location:</strong> ${location}</p>
    <p>${description}</p>
  `;
}

document.getElementById("prevBtn").onclick = function() {
  if (events.length === 0) return;
  current = (current - 1 + events.length) % events.length;
  showEvent(current);
};
document.getElementById("nextBtn").onclick = function() {
  if (events.length === 0) return;
  current = (current + 1) % events.length;
  showEvent(current);
};

// Touch swipe support (optional)
let startX = 0;
document.getElementById("eventBox").addEventListener("touchstart", e => {
  startX = e.touches[0].clientX;
});
document.getElementById("eventBox").addEventListener("touchend", e => {
  let endX = e.changedTouches[0].clientX;
  if (endX - startX > 50) {
    document.getElementById("prevBtn").click();
  } else if (startX - endX > 50) {
    document.getElementById("nextBtn").click();
  }
});

// Fetch events from backend
fetch('http://localhost:5000/events')
  .then(response => response.json())
  .then(data => {
    events = data;
    showEvent(current);
  })
  .catch(() => {
    document.getElementById("eventBox").innerHTML = "<p>Could not load events from backend.</p>";
  });