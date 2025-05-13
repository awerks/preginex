import { toast } from "./utils.js";

document.addEventListener("DOMContentLoaded", function () {

    var taskCalendarEl = document.getElementById("taskCalendar");

    var isMobile = window.innerWidth < 768;
    var defaultView = isMobile ? "listWeek" : "dayGridMonth";

    var headerConfig = isMobile
        ? { left: "prev,next", right: "today" }
        : { left: "title", right: "prev,next,dayGridMonth,timeGridWeek,timeGridDay,listWeek" };
    var taskCalendar = new FullCalendar.Calendar(taskCalendarEl, {
        initialView: defaultView,
        headerToolbar: headerConfig,
        height: "auto",
        events: GET_TASKS_URL,

        eventDidMount: function (info) {
            if (info.event.extendedProps.description) {
                tippy(info.el, {
                    content: "Description: " + info.event.extendedProps.description,
                    placement: "top",
                    arrow: true,
                });
            }
        },
        eventContent: function (arg) {
            let title = document.createElement("div");
            title.classList.add("fc-event-title");
            title.innerText = arg.event.title;

            let assignedTo = document.createElement("div");
            assignedTo.classList.add("fc-task-assigned");
            let assignedUsername = arg.event.extendedProps.assigned_username;
            if (assignedUsername == USERNAME) {
                assignedUsername = "you";
            }
            assignedTo.innerText = "Assigned to " + assignedUsername;

            let status = document.createElement("div");
            status.classList.add("fc-task-status");
            status.innerText = "Status: " + arg.event.extendedProps.status;
            if (arg.event.extendedProps.status === "Completed" && USER_ROLE === "Admin" || USER_ROLE === "Manager") {
                status.classList.add("completed");
                const deleteButton = document.createElement("button");
                deleteButton.innerText = "Delete";
                deleteButton.classList.add("fc-delete-btn");
                deleteButton.onclick = function () {
                    deleteTask(arg.event.extendedProps.task_id);
                };
                return { domNodes: [title, assignedTo, status, deleteButton] };
            }
            if (arg.event.extendedProps.status === 'Failed') {
                status.classList.add("failed");
            }
            if (arg.event.extendedProps.status === "Pending" && USER_ROLE === "Worker") {
                let completeButton = document.createElement("button");
                completeButton.innerText = "Complete";
                completeButton.classList.add("fc-approve-btn");
                completeButton.onclick = function () {
                    completeTask(arg.event.extendedProps.task_id, completeButton);
                };
                return { domNodes: [title, assignedTo, status, completeButton] };
            }
            return { domNodes: [title, assignedTo, status] };
        },
        // eventClick: function (info) {
        //     if (info.event.extendedProps.description) {
        //         alert("Description: " + info.event.extendedProps.description);
        //     }
        // }
    });

    taskCalendar.render();
    const taskForm = document.querySelector(".task-form");
    if (taskForm) {
        taskForm.addEventListener("submit", function (event) {
            const deadline = new Date(document.getElementById("deadline").value);
            const today = new Date();

            if (deadline < today) {
                event.preventDefault();
                toast("Deadline cannot be in the past.", "error");
                return;
            }
            toast("Task added successfully!", "success");
        });
    }

});

function completeTask(taskId, button) {
    const statusElement = document.querySelector(".fc-task-status");

    fetch(`${COMPLETE_TASK_URL}/${taskId}`, {
        method: "PATCH",
        headers: {
            "Content-Type": "application/json",
        },
    })
        .then((response) => {
            if (response.ok) {
                button.innerText = "Completed";
                button.disabled = true;
                button.classList.add("completed");
                statusElement.innerText = "Status: Completed";
                statusElement.classList.add("completed");
                toast("Task marked as completed!", "success");
            }
            else {
                button.innerText = "Failed";
                button.disabled = true;
                statusElement.innerText = "Status: Failed";
                statusElement.classList.add("failed");
                toast("Failed to mark task as completed.", "error");
            }
        }
        )
        .catch((error) => {
            console.error("Error:", error);
            toast("An error occurred while completing the task.", "error");
        });
}

function deleteTask(taskId) {
    fetch(`${DELETE_TASK_URL}/${taskId}`, {
        method: "DELETE",
        headers: {
            "Content-Type": "application/json",
        },
    })
        .then((response) => {
            if (response.ok) {
                toast("Task deleted successfully!", "success");
            } else {
                toast("Failed to delete task.", "error");
            }
            setTimeout(() => {
                location.reload();
            }, 1000);
        })
        .catch((error) => {
            console.error("Error:", error);
            toast("An error occurred while deleting the task.", "error");
        });
}