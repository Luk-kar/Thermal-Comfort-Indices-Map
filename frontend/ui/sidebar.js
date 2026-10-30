export function initializeSidebar({ onSelectImage, onOpacityChange }) {

  const files = document.getElementById("files");
  const opacity = document.getElementById("opacity");
  const opacityValue = document.getElementById("opacityVal");
  const fit = document.getElementById("fit");
  const status = document.getElementById("status");
  const state = { selectionId: 0 };

  function setStatus(message) {
    status.textContent = message;
  }

  opacity.addEventListener("input", () => {
    opacityValue.textContent = opacity.value;
    onOpacityChange(parseFloat(opacity.value));
  });

  function setFiles(names) {

    files.replaceChildren();

    if (!names.length) {
      setStatus("No PNGs configured. Check REGIONS and PNG_FILES.");
      return;
    }

    names.forEach(name => {

      const item = document.createElement("li");
      item.textContent = name;

      item.onclick = async () => {

        const selectionId = ++state.selectionId;

        files.querySelectorAll("li").forEach(element => element.classList.remove("active"));
        item.classList.add("active");
        setStatus("");

        try {
          await onSelectImage(name, { opacity: parseFloat(opacity.value), fit: fit.checked });
        } catch (error) {
          console.error("PNG selection failed:", error);
          if (selectionId === state.selectionId) {
            setStatus(`Failed to display the PNG: ${error.message || String(error)}`);
          }
        }
      };

      files.appendChild(item);
    });
    files.firstElementChild.click();
  }

  return { setFiles, setStatus };
}
