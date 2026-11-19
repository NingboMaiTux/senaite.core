import React from "react";

/**
 * Sidebar Header Component
 * Displays the toggle button for expanding/collapsing the sidebar
 */
export const SidebarHeader = ({isToggled, onToggle, label}) => {
  const iconClass = isToggled ? "fa fa-times" : "fa fa-bars";

  return (
    <div id="sidebar-header">
      <button
        type="button"
        onClick={onToggle}
        title={label}
        aria-label={label}
        aria-expanded={isToggled}>
        <i className={`sidebar-toggle-icon ${iconClass}`} />
      </button>
    </div>
  );
};
