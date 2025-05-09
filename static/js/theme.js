


let currentTheme = localStorage.getItem("theme");
if (!currentTheme) {
    currentTheme = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
applyTheme(currentTheme);

window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    if (!localStorage.getItem("theme")) {
        const newColorScheme = e.matches ? "dark" : "light";
        applyTheme(newColorScheme);
    }
});

function applyTheme(theme) {
    if (theme === "dark") {
        document.documentElement.setAttribute("data-theme", "dark");
    } else {
        document.documentElement.setAttribute("data-theme", "light");
    }
}
function saveThemePreference(theme) {
    localStorage.setItem("theme", theme);
}

document.addEventListener("DOMContentLoaded", function () {
    const themeToggle = document.getElementById("theme-checkbox");
    const spinMe = document.getElementById("spin-me");
    if (spinMe) {
        spinMe.addEventListener("click", spinFunction);
    }
    if (themeToggle) {
        const currentTheme = localStorage.getItem("theme");
        if (document.documentElement.getAttribute("data-theme") === "dark" || currentTheme === "dark") {
            themeToggle.checked = true;
        }
        themeToggle.addEventListener("change", function () {
            if (this.checked) {
                applyTheme("dark");
                saveThemePreference("dark");
                this.checked = true;
            } else {
                applyTheme("light");
                saveThemePreference("light");
                this.checked = false;
            }
        });
    }
});

function spinFunction() {
    const root = document.documentElement;
    const spintime = 15 * 1000;
    root.style.setProperty("--spintime", spintime + "ms");
    root.classList.add("spin");
    root.style.overflow = "hidden";
    const onClick = () => cleanUp();
    const timeoutId = setTimeout(cleanUp, spintime);

    document.addEventListener("click", onClick, { once: true, capture: true });

    function cleanUp() {
        root.classList.remove("spin");
        root.style.overflow = null;
        root.style.setProperty("--spintime", null);
        clearTimeout(timeoutId);
        document.removeEventListener("click", onClick, { capture: true });
    }
}