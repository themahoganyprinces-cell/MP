class MyCalendar extends HTMLElement {

  constructor() {
    super();
    this.currentDate      = new Date();
    this.selectedDate     = null;
    this.availableDates   = new Set();
    this.requestDates     = new Set();
    this.requestWithSlots = new Set();
    this.availabilityLoaded = false;
  }

  connectedCallback() {
    this.render();
    this._dispatchMonthChanged();
  }

  setMarkedDates(data) {
    this.availableDates   = new Set(data.available          || []);
    this.requestDates     = new Set(data.request            || []);
    this.requestWithSlots = new Set(data.request_with_slots || []);
    this.availabilityLoaded = true;
    this.render();
  }

  _dispatchMonthChanged() {
    const year  = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth() + 1;
    this.dispatchEvent(new CustomEvent("monthChanged", { detail: { year, month } }));
  }

  render() {
    const year  = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();

    const monthNames = [
      "January","February","March","April","May","June",
      "July","August","September","October","November","December"
    ];

    const firstDay    = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    this.innerHTML = `
      <div class="calendar">
        <div class="header">
          <button id="prevMonth">&#8592;</button>
          <div class="month-year">${monthNames[month]} ${year}</div>
          <button id="nextMonth">&#8594;</button>
        </div>
        <div class="weekdays">
          <div>Sun</div><div>Mon</div><div>Tue</div>
          <div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div>
        </div>
        <div class="days" id="daysContainer"></div>
        <div class="calendar-key">
          <span class="key-dot"></span><span>Availability present on request date</span>
        </div>
      </div>
    `;

    const daysContainer = this.querySelector("#daysContainer");

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    for (let i = 0; i < firstDay; i++) {
      const empty = document.createElement("div");
      empty.classList.add("day", "empty");
      daysContainer.appendChild(empty);
    }

    for (let day = 1; day <= daysInMonth; day++) {
      const dayDiv = document.createElement("div");
      dayDiv.classList.add("day");
      dayDiv.innerText = day;

      const mm      = String(month + 1).padStart(2, '0');
      const dd      = String(day).padStart(2, '0');
      const dateStr = `${year}-${mm}-${dd}`;
      const dateObj = new Date(year, month, day);

      if (day === today.getDate() && month === today.getMonth() && year === today.getFullYear()) {
        dayDiv.classList.add("today");
      }

      if (this.selectedDate &&
          this.selectedDate.day === day &&
          this.selectedDate.month === month + 1 &&
          this.selectedDate.year === year) {
        dayDiv.classList.add("selected");
      }

      const isPast      = dateObj < today;
      const isAvailable = this.availabilityLoaded && this.availableDates.has(dateStr);
      const isRequest   = this.availabilityLoaded && (
                            this.requestDates.has(dateStr) || this.requestWithSlots.has(dateStr)
                          );

      if (isPast || (this.availabilityLoaded && !isAvailable && !isRequest)) {
        dayDiv.classList.add("unavailable");
        daysContainer.appendChild(dayDiv);
        continue;
      }

      if (isAvailable) {
        dayDiv.classList.add("available");
      } else if (isRequest) {
        dayDiv.classList.add("request");
        if (this.requestWithSlots.has(dateStr)) {
          dayDiv.classList.add("has-availability");
        }
      }

      dayDiv.addEventListener("click", () => {
        this.querySelectorAll(".day").forEach(d => d.classList.remove("selected"));
        dayDiv.classList.add("selected");
        this.selectedDate = { day, month: month + 1, year };
        const dateType = isAvailable ? 'available' : 'request';
        this.dispatchEvent(new CustomEvent("dateSelected", {
          detail: { ...this.selectedDate, dateType }
        }));
      });

      daysContainer.appendChild(dayDiv);
    }

    this.querySelector("#prevMonth").addEventListener("click", () => {
      this.currentDate.setMonth(this.currentDate.getMonth() - 1);
      this.availabilityLoaded = false;
      this.availableDates   = new Set();
      this.requestDates     = new Set();
      this.requestWithSlots = new Set();
      this.render();
      this._dispatchMonthChanged();
    });

    this.querySelector("#nextMonth").addEventListener("click", () => {
      this.currentDate.setMonth(this.currentDate.getMonth() + 1);
      this.availabilityLoaded = false;
      this.availableDates   = new Set();
      this.requestDates     = new Set();
      this.requestWithSlots = new Set();
      this.render();
      this._dispatchMonthChanged();
    });
  }
}

customElements.define("my-calendar", MyCalendar);
