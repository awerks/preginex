
export const toast = (msg, icon = 'success') =>
    Swal.fire({
        toast: true, position: 'bottom-end', icon, title: msg,
        showConfirmButton: false, timer: 2200
    });
export const confirmBox = (msg, confirmText = 'Yes, do it!') =>
    Swal.fire({
        title: msg, icon: 'warning',
        showCancelButton: true, focusCancel: true,
        confirmButtonText: confirmText, cancelButtonText: 'Cancel'
    }).then(res => res.isConfirmed);