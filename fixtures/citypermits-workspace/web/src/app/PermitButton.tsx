import React from "react";

export function PermitButton() {
  fetch(`${PERMITS_API}/api/permits/motor-vehicle`, { method: "POST" });
  fetch(`${PERMITS_API}/api/permits/residential`, { method: "POST" });
  fetch(`${PERMITS_API}/api/permits/commercial`, { method: "POST" });
  fetch(`${PERMITS_API}/api/permits/renewal`, { method: "POST" });
  fetch(`${PERMITS_API}/api/permits/status`, { method: "GET" });
  return null;
}
