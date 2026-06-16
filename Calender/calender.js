class MyCalendar extends HTMLElement {

  constructor() {
    super();
    this.currentDate = new Date();
    this.selectedDate = null;
  }

  connectedCallback() {
    this.render();
  }

  render() {

    const year = this.currentDate.getFullYear();
    const month = this.currentDate.getMonth();

    const monthNames = [
      "January","February","March","April","May","June",
      "July","August","September","October","November","December"
    ];

    const firstDay = new Date(year, month, 1).getDay();
    const daysInMonth = new Date(year, month + 1, 0).getDate();

    this.innerHTML = `
      <div class="calendar">

        <div class="header">

          <button id="prevMonth">←</button>

          <div class="month-year">
            ${monthNames[month]} ${year}
          </div>

          <button id="nextMonth">→</button>

        </div>

        <div class="weekdays">
          <div>Sun</div><div>Mon</div><div>Tue</div>
          <div>Wed</div><div>Thu</div><div>Fri</div><div>Sat</div>
        </div>

        <div class="days" id="daysContainer"></div>

      </div>
    `;

    const daysContainer = this.querySelector("#daysContainer");

    for (let i = 0; i < firstDay; i++) {
      const empty = document.createElement("div");
      empty.classList.add("day", "empty");
      daysContainer.appendChild(empty);
    }

    const today = new Date();

    for (let day = 1; day <= daysInMonth; day++) {

      const dayDiv = document.createElement("div");
      dayDiv.classList.add("day");
      dayDiv.innerText = day;

      if (
        day === today.getDate() &&
        month === today.getMonth() &&
        year === today.getFullYear()
      ) {
        dayDiv.classList.add("today");
      }

      dayDiv.addEventListener("click", () => {

        this.querySelectorAll(".day")
          .forEach(d => d.classList.remove("selected"));

        dayDiv.classList.add("selected");

        this.selectedDate = { day, month: month + 1, year };

        console.log("Selected:", this.selectedDate);

        this.dispatchEvent(new CustomEvent("dateSelected", {
          detail: this.selectedDate
        }));

      });

      daysContainer.appendChild(dayDiv);
    }

    this.querySelector("#prevMonth").addEventListener("click", () => {
      this.currentDate.setMonth(this.currentDate.getMonth() - 1);
      this.render();
    });

    this.querySelector("#nextMonth").addEventListener("click", () => {
      this.currentDate.setMonth(this.currentDate.getMonth() + 1);
      this.render();
    });
  }
}

customElements.define("my-calendar", MyCalendar);