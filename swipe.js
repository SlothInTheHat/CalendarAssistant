// Array to hold event data fetched from the backend
let events = [];
// Index of the currently displayed event
let current = 0;

/**
 * Displays the event at the given index in the eventBox div.
 * Handles missing fields and makes URLs in the description clickable.
 */
function showEvent(idx) {
  if (events.length === 0) {
    document.getElementById("eventBox").innerHTML = "<p>No events found.</p>";
    return;
  }
  const e = events[idx];
  // Use fallback values if fields are missing
  const date = e.date || e.start_date || "N/A";
  const time = e.time ||
    ((e.start_time ? e.start_time : "") +
     (e.end_time ? " - " + e.end_time : "")) || "N/A";
  const location = e.location || "N/A";
  // If description is a URL, make it clickable
  const description = e.description
    ? (e.description.startsWith("http")
        ? `<a href="${e.description}" target="_blank">${e.description}</a>`
        : e.description)
    : "N/A";

  // Render the event details in the eventBox
  document.getElementById("eventBox").innerHTML = `
    <h2>${e.title || "Untitled Event"}</h2>
    <p><strong>Date:</strong> ${date}</p>
    <p><strong>Time:</strong> ${time}</p>
    <p><strong>Location:</strong> ${location}</p>
    <p>${description}</p>
  `;
}

// Show previous event when left arrow button is clicked
document.getElementById("prevBtn").onclick = function() {
  if (events.length === 0) return;
  current = (current - 1 + events.length) % events.length;
  showEvent(current);
};

// Show next event when right arrow button is clicked
document.getElementById("nextBtn").onclick = function() {
  if (events.length === 0) return;
  current = (current + 1) % events.length;
  showEvent(current);
};

// Touch swipe support for mobile devices
let startX = 0;
document.getElementById("eventBox").addEventListener("touchstart", e => {
  startX = e.touches[0].clientX;
});
document.getElementById("eventBox").addEventListener("touchend", e => {
  let endX = e.changedTouches[0].clientX;
  // Swipe right: show previous event
  if (endX - startX > 50) {
    document.getElementById("prevBtn").click();
  // Swipe left: show next event
  } else if (startX - endX > 50) {
    document.getElementById("nextBtn").click();
  }
});

// Fetch events from the backend API and display the first event
fetch('http://localhost:5000/events')
  .then(response => response.json())
  .then(data => {
    events = data;
    showEvent(current);
  })
  .catch(() => {
    // Show error message if backend is unreachable
    document.getElementById("eventBox").innerHTML = "<p>Could not load events from backend.</p>";
  });