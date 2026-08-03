/** DX SENAITE Setup Controller
 *
 * This controller is loaded for the new DX SENAITE Setup edit view, e.g.:
 * `/senaite/setup/edit`
 *
 */
function SenaiteSetupEditView() {
    const that = this;
    const pageSelector = "body.portaltype-setup.template-edit, .portaltype-setup.template-edit";
    const userSelector = "input[type='checkbox'][name^='form.widgets.restrict_worksheet_users_access']";
    const managementSelector = "input[type='checkbox'][name^='form.widgets.restrict_worksheet_management']";

    /**
     * Entry-point method for SenaiteSetupEditView
     */
    that.load = function () {
        if ($(pageSelector).length === 0) {
            return;
        }

        const $userAccess = $(userSelector);
        const $management = $(managementSelector);

        if ($userAccess.length === 0 || $management.length === 0) {
            return;
        }

        // 中文注释：DX Setup 使用 AJAX 联动字段状态，这里在前端再补一层
        // checkbox 勾选态同步，确保用户能看到“已勾选再禁用”的真实状态。
        const syncManagementState = function () {
            if ($userAccess.is(":checked")) {
                $management.prop("checked", true);
                $management.attr("checked", "checked");
                $management.prop("disabled", true);
            } else {
                $management.prop("disabled", false);
            }
        };

        $(document).on("change", userSelector, function () {
            syncManagementState();
        });

        $(document).ajaxStop(function () {
            syncManagementState();
        });

        syncManagementState();
    };
}
