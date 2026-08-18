import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  BriefcaseBusiness,
  Building2,
  CalendarDays,
  CalendarOff,
  ChartNoAxesGantt,
  CirclePlus,
  Clock3,
  PlaneTakeoff,
  UsersRound,
  X
} from "lucide-react";
import "./styles.css";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:5000";
const departments = ["Engineering", "Operations", "Analytics"];
const leaveTypes = ["Vacation", "Medical", "Personal", "Training"];

const fallbackPlanning = {
  employees: [],
  projects: [],
  assignments: [],
  leaves: []
};

function App() {
  const [planning, setPlanning] = useState(fallbackPlanning);
  const [activePage, setActivePage] = useState("schedule");
  const [activeModal, setActiveModal] = useState("");
  const [isLoading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadPlanning = async () => {
    setError("");
    try {
      const response = await fetch(`${API_BASE}/api/planning`);
      if (!response.ok) throw new Error("Planning API failed");
      setPlanning(await response.json());
    } catch {
      setError("The API is not reachable yet. Start Triweb.Api to load live planning data.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPlanning();
  }, []);

  const calendarDays = useMemo(() => buildCalendarDays(planning.assignments, planning.leaves), [planning]);
  const metrics = useMemo(() => buildMetrics(planning), [planning]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <img className="brand-logo" src="/triweb-logo.svg" alt="Triweb" />
          <div>
            <strong>Triweb</strong>
            <span>APS Control</span>
          </div>
        </div>

        <nav className="nav-stack" aria-label="Primary">
          <button className={`nav-item ${activePage === "schedule" ? "active" : ""}`} onClick={() => setActivePage("schedule")}>
            <ChartNoAxesGantt size={18} />Schedule
          </button>
          <button className={`nav-item ${activePage === "employees" ? "active" : ""}`} onClick={() => setActivePage("employees")}>
            <UsersRound size={18} />Employees
          </button>
          <button className={`nav-item ${activePage === "leaves" ? "active" : ""}`} onClick={() => setActivePage("leaves")}>
            <PlaneTakeoff size={18} />Leaves
          </button>
          <button className={`nav-item ${activePage === "projects" ? "active" : ""}`} onClick={() => setActivePage("projects")}>
            <BriefcaseBusiness size={18} />Projects
          </button>
        </nav>
      </aside>

      <section className="workspace">
        <header className="hero">
          <div className="hero-copy">
            <p className="eyebrow">Advanced Planning and Scheduling</p>
            <h1>{activePage === "leaves" ? "Leave Planning" : "Employee Planning"}</h1>
            <p>Automatic project allocation across teams, departments, calendar capacity, and planned employee absence.</p>
          </div>
          <div className="hero-actions">
            <button className="secondary-action light" onClick={() => setActiveModal("leave")}>
              <CalendarOff size={18} />Add Leave
            </button>
            <button className="primary-action" onClick={() => setActiveModal("project")}>
              <CirclePlus size={18} />New Project
            </button>
          </div>
        </header>

        <section className="metrics" aria-label="Planning summary">
          <Metric icon={<UsersRound size={18} />} label="Employees" value={metrics.employees} />
          <Metric icon={<Building2 size={18} />} label="Departments" value={metrics.departments} />
          <Metric icon={<BriefcaseBusiness size={18} />} label="Projects" value={metrics.projects} />
          <Metric icon={<CalendarOff size={18} />} label="Planned Leaves" value={metrics.leaves} />
        </section>

        {error && <div className="notice">{error}</div>}
        {isLoading ? <div className="loading">Loading planning board...</div> : (
          <>
            {activePage === "schedule" && (
              <div className="content-grid">
                <section className="schedule-panel" id="schedule">
                  <div className="panel-heading">
                    <div>
                      <p className="eyebrow">Calendar</p>
                      <h2>Team Allocation</h2>
                    </div>
                    <span>{calendarDays.length} days visible</span>
                  </div>
                  <ScheduleGrid planning={planning} days={calendarDays} />
                </section>

                <section className="side-panel">
                  <div className="panel-heading compact">
                    <div>
                      <p className="eyebrow">Availability</p>
                      <h2>Upcoming Leave</h2>
                    </div>
                  </div>
                  <LeaveList planning={planning} compact />
                </section>
              </div>
            )}

            {activePage === "employees" && (
              <section className="wide-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Profiles</p>
                    <h2>Employees</h2>
                  </div>
                </div>
                <EmployeeList employees={planning.employees} />
              </section>
            )}

            {activePage === "leaves" && (
              <section className="wide-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Absence</p>
                    <h2>Planned Leaves and Vacations</h2>
                  </div>
                  <button className="primary-action" onClick={() => setActiveModal("leave")}>
                    <CalendarOff size={18} />Add Leave
                  </button>
                </div>
                <LeaveList planning={planning} />
              </section>
            )}

            {activePage === "projects" && (
              <section className="wide-panel">
                <div className="panel-heading">
                  <div>
                    <p className="eyebrow">Portfolio</p>
                    <h2>Projects</h2>
                  </div>
                  <button className="primary-action" onClick={() => setActiveModal("project")}>
                    <CirclePlus size={18} />New Project
                  </button>
                </div>
                <ProjectList projects={planning.projects} />
              </section>
            )}
          </>
        )}
      </section>

      {activeModal === "project" && (
        <ProjectModal
          onClose={() => setActiveModal("")}
          onCreated={() => {
            setActiveModal("");
            loadPlanning();
          }}
        />
      )}

      {activeModal === "leave" && (
        <LeaveModal
          employees={planning.employees}
          onClose={() => setActiveModal("")}
          onCreated={() => {
            setActiveModal("");
            loadPlanning();
          }}
        />
      )}
    </main>
  );
}

function Metric({ icon, label, value }) {
  return (
    <article className="metric">
      <div className="metric-icon">{icon}</div>
      <span>{label}</span>
      <strong>{value}</strong>
    </article>
  );
}

function ScheduleGrid({ planning, days }) {
  const projectById = new Map(planning.projects.map((project) => [project.id, project]));
  const taskById = new Map(planning.projects.flatMap((project) => project.tasks.map((task) => [task.id, task])));

  if (!planning.employees.length) {
    return <div className="empty-state">No planning data yet.</div>;
  }

  return (
    <div className="schedule-scroll">
      <div className="schedule-grid" style={{ "--day-count": days.length }}>
        <div className="corner-cell">Employees</div>
        {days.map((day) => (
          <div className={`day-header ${isWeekend(day) ? "weekend" : ""}`} key={day}>
            <span>{formatDay(day)}</span>
          </div>
        ))}

        {planning.employees.map((employee) => (
          <React.Fragment key={employee.id}>
            <div className="employee-cell">
              <strong>{employee.id}</strong>
              <span>{employee.fullName}</span>
            </div>
            {days.map((day) => {
              const assignment = planning.assignments.find((item) =>
                item.employeeId === employee.id && item.startDate <= day && item.endDate >= day
              );
              const leave = planning.leaves.find((item) =>
                item.employeeId === employee.id && item.startDate <= day && item.returnDate > day
              );
              const project = assignment ? projectById.get(assignment.projectId) : null;
              const task = assignment ? taskById.get(assignment.taskId) : null;
              return (
                <div className={`day-cell ${isWeekend(day) ? "weekend" : ""}`} key={`${employee.id}-${day}`}>
                  {assignment && (
                    <div
                      className="assignment"
                      style={{ backgroundColor: assignment.color }}
                      title={`${project?.name ?? assignment.projectId}: ${task?.name ?? assignment.taskId}`}
                    >
                      <span>{assignment.projectId}</span>
                    </div>
                  )}
                  {!assignment && leave && (
                    <div className="leave-chip" title={`${leave.type}: returns ${formatDate(leave.returnDate)}`}>
                      <span>{leave.type}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </React.Fragment>
        ))}
      </div>
    </div>
  );
}

function EmployeeList({ employees }) {
  return (
    <div className="employee-list expanded">
      {employees.map((employee) => (
        <article className="employee-card" key={employee.id}>
          <div>
            <strong>{employee.fullName}</strong>
            <span>{employee.id} - {employee.teamId}</span>
          </div>
          <p>{employee.role}</p>
          <footer>
            <span>{employee.department}</span>
            <span>{employee.yearsOfExperience} yrs</span>
          </footer>
        </article>
      ))}
    </div>
  );
}

function LeaveList({ planning, compact = false }) {
  const employeeById = new Map(planning.employees.map((employee) => [employee.id, employee]));
  const leaves = [...planning.leaves].sort((a, b) => a.startDate.localeCompare(b.startDate));

  if (!leaves.length) {
    return <div className="empty-state">No planned leaves yet.</div>;
  }

  return (
    <div className={`leave-list ${compact ? "compact-list" : ""}`}>
      {leaves.map((leave) => {
        const employee = employeeById.get(leave.employeeId);
        return (
          <article className="leave-card" key={leave.id}>
            <div className="leave-card-main">
              <span className={`leave-type ${leave.type.toLowerCase()}`}>{leave.type}</span>
              <div>
                <strong>{employee?.fullName ?? leave.employeeId}</strong>
                <span>{leave.employeeId} - {employee?.department ?? "Unknown department"}</span>
              </div>
            </div>
            <div className="leave-dates">
              <span>{formatDate(leave.startDate)}</span>
              <span>Return {formatDate(leave.returnDate)}</span>
            </div>
            {!compact && <p>{leave.notes || "No notes"}</p>}
          </article>
        );
      })}
    </div>
  );
}

function ProjectList({ projects }) {
  return (
    <div className="project-list">
      {projects.map((project) => (
        <article className="project-card" key={project.id}>
          <div>
            <strong>{project.name}</strong>
            <span>{project.id} - {formatDate(project.startDate)} to {formatDate(project.deadline)}</span>
          </div>
          <footer>{project.tasks.length} tasks required</footer>
        </article>
      ))}
    </div>
  );
}

function ProjectModal({ onClose, onCreated }) {
  const [name, setName] = useState("");
  const [startDate, setStartDate] = useState("2026-08-17");
  const [deadline, setDeadline] = useState("2026-08-28");
  const [tasks, setTasks] = useState([
    { name: "Requirements planning", department: "Operations", estimatedDays: 3 },
    { name: "Scheduler integration", department: "Engineering", estimatedDays: 5 },
    { name: "Performance report", department: "Analytics", estimatedDays: 2 }
  ]);
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const updateTask = (index, patch) => {
    setTasks((current) => current.map((task, taskIndex) => taskIndex === index ? { ...task, ...patch } : task));
  };

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE}/api/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, startDate, deadline, tasks })
      });

      if (!response.ok) {
        const details = await response.json();
        throw new Error(details.message ?? "Project could not be created.");
      }

      onCreated();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal" onSubmit={submit}>
        <ModalHeader eyebrow="Scheduler Input" title="New Project" onClose={onClose} />

        <label>
          Project name
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder="Warehouse Optimization" required />
        </label>

        <div className="form-row">
          <label>
            Start date
            <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
          </label>
          <label>
            Deadline
            <input type="date" value={deadline} onChange={(event) => setDeadline(event.target.value)} required />
          </label>
        </div>

        <div className="task-editor">
          <div className="task-editor-heading">
            <span>Tasks Required</span>
            <button type="button" onClick={() => setTasks((current) => [...current, { name: "", department: "Engineering", estimatedDays: 1 }])}>
              Add Task
            </button>
          </div>
          {tasks.map((task, index) => (
            <div className="task-row" key={index}>
              <input value={task.name} onChange={(event) => updateTask(index, { name: event.target.value })} placeholder="Task name" required />
              <select value={task.department} onChange={(event) => updateTask(index, { department: event.target.value })}>
                {departments.map((department) => <option key={department}>{department}</option>)}
              </select>
              <input type="number" min="1" max="20" value={task.estimatedDays} onChange={(event) => updateTask(index, { estimatedDays: Number(event.target.value) })} aria-label="Estimated days" />
            </div>
          ))}
        </div>

        {error && <div className="form-error">{error}</div>}

        <footer>
          <button type="button" className="secondary-action" onClick={onClose}>Cancel</button>
          <button type="submit" className="primary-action" disabled={isSaving}>
            <CalendarDays size={18} />{isSaving ? "Scheduling..." : "Schedule Project"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function LeaveModal({ employees, onClose, onCreated }) {
  const [employeeId, setEmployeeId] = useState(employees[0]?.id ?? "");
  const [type, setType] = useState("Vacation");
  const [startDate, setStartDate] = useState("2026-08-17");
  const [returnDate, setReturnDate] = useState("2026-08-24");
  const [notes, setNotes] = useState("");
  const [isSaving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE}/api/leaves`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employeeId, type, startDate, returnDate, notes })
      });

      if (!response.ok) {
        const details = await response.json();
        throw new Error(details.message ?? "Leave could not be created.");
      }

      onCreated();
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <form className="modal compact-modal" onSubmit={submit}>
        <ModalHeader eyebrow="Availability" title="Add Planned Leave" onClose={onClose} />

        <label>
          Employee
          <select value={employeeId} onChange={(event) => setEmployeeId(event.target.value)} required>
            {employees.map((employee) => (
              <option value={employee.id} key={employee.id}>{employee.fullName} - {employee.id}</option>
            ))}
          </select>
        </label>

        <div className="form-row">
          <label>
            Type
            <select value={type} onChange={(event) => setType(event.target.value)}>
              {leaveTypes.map((leaveType) => <option key={leaveType}>{leaveType}</option>)}
            </select>
          </label>
          <label>
            Start date
            <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} required />
          </label>
        </div>

        <label>
          Return date
          <input type="date" value={returnDate} onChange={(event) => setReturnDate(event.target.value)} required />
        </label>

        <label>
          Notes
          <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder="Annual vacation, training, medical leave..." />
        </label>

        {error && <div className="form-error">{error}</div>}

        <footer>
          <button type="button" className="secondary-action" onClick={onClose}>Cancel</button>
          <button type="submit" className="primary-action" disabled={isSaving}>
            <CalendarOff size={18} />{isSaving ? "Saving..." : "Save Leave"}
          </button>
        </footer>
      </form>
    </div>
  );
}

function ModalHeader({ eyebrow, title, onClose }) {
  return (
    <header>
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      <button className="icon-button" type="button" onClick={onClose} aria-label="Close">
        <X size={18} />
      </button>
    </header>
  );
}

function buildCalendarDays(assignments, leaves) {
  const ranges = [
    ...assignments.map((assignment) => [assignment.startDate, assignment.endDate]),
    ...leaves.map((leave) => [leave.startDate, leave.returnDate])
  ];

  if (!ranges.length) return [];

  const starts = ranges.map(([start]) => new Date(`${start}T00:00:00`));
  const ends = ranges.map(([, end]) => new Date(`${end}T00:00:00`));
  const start = new Date(Math.min(...starts));
  const end = new Date(Math.max(...ends));
  const days = [];

  for (const cursor = new Date(start); cursor <= end; cursor.setDate(cursor.getDate() + 1)) {
    days.push(cursor.toISOString().slice(0, 10));
  }

  return days;
}

function buildMetrics(planning) {
  const departments = new Set(planning.employees.map((employee) => employee.department));

  return {
    employees: planning.employees.length,
    departments: departments.size,
    projects: planning.projects.length,
    leaves: planning.leaves.length
  };
}

function formatDay(value) {
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString("en", { month: "short", day: "numeric" });
}

function formatDate(value) {
  const date = new Date(`${value}T00:00:00`);
  return date.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" });
}

function isWeekend(value) {
  const day = new Date(`${value}T00:00:00`).getDay();
  return day === 0 || day === 6;
}

createRoot(document.getElementById("root")).render(<App />);
