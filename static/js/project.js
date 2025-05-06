function htmlTitle(html) {
    const container = document.createElement("div");
    container.style.fontFamily = window.getComputedStyle(document.body).fontFamily;
    container.innerHTML = html;
    return container;
}

document.addEventListener("DOMContentLoaded", function () {
    document.querySelector(".project-form").addEventListener("submit", function (event) {
        var startDate = new Date(document.getElementById("start_date").value);
        var endDate = new Date(document.getElementById("end_date").value);
        if (startDate > endDate) {
            event.preventDefault();
            alert("End date must be after start date.");
        }
    });

    fetch(PROJECTS_URL)
        .then((response) => response.json())
        .then((data) => {
            let nodes = [];
            let edges = [];

            data.forEach((project) => {
                if (!project.tasks || project.tasks.length === 0) {
                    return;
                }
                let projectId = "p" + project.project_id;
                nodes.push({
                    id: projectId,
                    label: project.project_name,
                    title: htmlTitle(
                        "<span style='color: #e91e63;'><i class='fas fa-info-circle'></i> Project Description: " +
                        project.description +
                        "</span><br>" +
                        "<span style='color: #3f51b5;'><i class='fas fa-calendar-alt'></i> Start: " +
                        project.start +
                        "</span><br>" +
                        "<span style='color: #4caf50;'><i class='fas fa-calendar-check'></i> End: " +
                        project.end +
                        "</span><br>" +
                        "<span style='color: black;'><i class='fas fa-user'></i> Manager: " +
                        project.manager +
                        "</span>",
                    ),
                    //title: "Project Description: " + project.description + "\nStart: " + project.start + "\nEnd: " + project.end + "\nManager: " + project.manager,
                    shape: "box",
                    color: "#6200ee",
                    font: { color: "#ffffff", size: 16 },
                    borderWidth: 2,
                    margin: 10,
                });

                project.tasks.forEach((task) => {
                    let taskId = "t" + task.task_id;
                    nodes.push({
                        id: taskId,
                        label: task.task_name,
                        title: htmlTitle(
                            "<span style='color: #e91e63;'><i class='fas fa-info-circle'></i> Task Description: " +
                            task.description +
                            "</span><br>" +
                            "<span style='color: #3f51b5;'><i class='fas fa-calendar-alt'></i> Deadline: " +
                            task.end +
                            "</span><br>" +
                            "<span style='color: " +
                            (task.status === "Completed"
                                ? "#4caf50"
                                : task.status === "Pending"
                                    ? "#ff9800"
                                    : "#2196f3") +
                            ";'><i class='fas fa-check'></i> Status: " +
                            task.status +
                            "</span>",
                        ),
                        shape: "ellipse",
                        color:
                            task.status === "Completed"
                                ? "#4caf50"
                                : task.status === "Pending"
                                    ? "#ff9800"
                                    : "#2196f3",
                        font: { color: "#ffffff", size: 14 },
                        borderWidth: 1,
                    });
                    edges.push({
                        from: projectId,
                        to: taskId,
                        arrows: "to",
                        color: { color: "#848484" },
                        smooth: { enabled: true, type: "cubicBezier", roundness: 0.5 },
                    });
                });
            });

            let container = document.getElementById("projectGraph");
            let visData = {
                nodes: new vis.DataSet(nodes),
                edges: new vis.DataSet(edges),
            };

            let options = {

                interaction: {
                    hover: true,
                    zoomView: true,
                    dragView: true,
                },

            };
            // let options = { physics: { enabled: true }, interaction: { hover: true, zoomView: false, dragView: false } };

            let network = new vis.Network(container, visData, options);

            document.getElementById("resetLayoutBtn").addEventListener("click", function () {
                network.fit({
                    animation: {
                        duration: 800,
                        easingFunction: "easeInOutQuad",
                    },
                });
            });
        })
        .catch((error) => console.error("Error fetching project data:", error));
});