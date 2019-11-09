import datetime
from difflib import Differ
from functools import cmp_to_key
from .models import get_calendars, Calendar, Trip

differ = Differ(charjunk=lambda _: True)


def get_journey_patterns(trips):
    trips = trips.prefetch_related('stoptime_set')

    patterns = []
    pattern_hashes = set()

    for trip in trips:
        pattern = [stoptime.stop_code for stoptime in trip.stoptime_set.all()]
        pattern_hash = str(pattern)
        if pattern_hash not in pattern_hashes:
            patterns.append(pattern)
            pattern_hashes.add(pattern_hash)

    return patterns


def get_stop_usages(trips):
    groupings = [[], []]

    trips = trips.prefetch_related('stoptime_set')

    for trip in trips:
        if trip.inbound:
            grouping = 1
        else:
            grouping = 0
        rows = groupings[grouping]

        new_rows = [stoptime.stop_code for stoptime in trip.stoptime_set.all()]
        diff = differ.compare(rows, new_rows)

        y = 0  # how many rows down we are

        for stoptime in trip.stoptime_set.all():
            if y < len(rows):
                existing_row = rows[y]
            else:
                existing_row = None

            instruction = next(diff)

            while instruction[0] in '-?':
                if instruction[0] == '-':
                    y += 1
                    if y < len(rows):
                        existing_row = rows[y]
                    else:
                        existing_row = None
                instruction = next(diff)

            assert instruction[2:] == stoptime.stop_code

            if instruction[0] == '+':
                if not existing_row:
                    rows.append(stoptime.stop_code)
                else:
                    rows = groupings[grouping] = rows[:y] + [stoptime.stop_code] + rows[y:]
                existing_row = stoptime.stop_code
            else:
                assert instruction[2:] == existing_row

            y += 1

    return groupings


class Timetable:
    def __init__(self, routes, date):
        self.routes = routes
        self.groupings = [Grouping(), Grouping(True)]

        self.date = date

        self.calendars = Calendar.objects.filter(trip__route__in=routes).distinct()

        if not routes:
            return

        if not self.date:
            for date in self.date_options():
                self.date = date
                break
        if not self.date:
            return

        trips = Trip.objects.filter(calendar__in=get_calendars(self.date),
                                    route__in=routes).order_by('start').prefetch_related('notes')

        trips = list(trips.prefetch_related('stoptime_set'))

        for trip in trips:
            if trip.inbound:
                grouping = self.groupings[1]
            else:
                grouping = self.groupings[0]
            grouping.trips.append(trip)

        for grouping in self.groupings:
            grouping.trips.sort(key=cmp_to_key(Trip.__cmp__))
            for trip in grouping.trips:
                grouping.handle_trip(trip)

        if all(g.trips for g in self.groupings):
            self.groupings.sort(key=Grouping.get_order)

        for grouping in self.groupings:
            for row in grouping.rows:
                row.has_waittimes = any(type(cell) is Cell and cell.wait_time for cell in row.times)
            grouping.do_heads_and_feet()

    def date_options(self):
        date = datetime.date.today()
        start_dates = [route.start_date for route in self.routes if route.start_date]
        if start_dates:
            date = max(date, max(start_dates))

        end_date = date + datetime.timedelta(days=21)
        end_dates = [route.end_date for route in self.routes if route.end_date]
        if end_dates:
            end_date = min(end_date, max(end_dates))

        if self.date and self.date < date:
            yield self.date
        while date <= end_date:
            if any(getattr(calendar, date.strftime('%a').lower()) for calendar in self.calendars):
                yield date
            date += datetime.timedelta(days=1)
        if self.date and self.date > end_date:
            yield self.date

    def has_set_down_only(self):
        for grouping in self.groupings:
            for row in grouping.rows:
                for cell in row.times:
                    if type(cell) is Cell and cell.stoptime.activity == 'setDown':
                        return True


class Repetition:
    """Represents a special cell in a timetable, spanning multiple rows and columns,
    with some text like 'then every 5 minutes until'.
    """
    def __init__(self, colspan, rowspan, duration):
        self.colspan = colspan
        self.rowspan = self.min_height = rowspan
        self.duration = duration

    def __str__(self):
        # cleverly add non-breaking spaces if there aren't many rows
        if self.duration.seconds == 3600:
            if self.min_height < 3:
                return 'then\u00A0hourly until'
            return 'then hourly until'
        if self.duration.seconds % 3600 == 0:
            duration = '{} hours'.format(int(self.duration.seconds / 3600))
        else:
            duration = '{} minutes'.format(int(self.duration.seconds / 60))
        if self.min_height < 3:
            return 'then\u00A0every {}\u00A0until'.format(duration.replace(' ', '\u00A0'))
        if self.min_height < 4:
            return 'then every\u00A0{} until'.format(duration.replace(' ', '\u00A0'))
        return 'then every {} until'.format(duration)


def abbreviate(grouping, i, in_a_row, difference):
    """Given a Grouping, and a timedelta, modify each row and..."""
    seconds = difference.total_seconds()
    if not seconds or (seconds != 3600 and seconds > 1800):  # neither hourly nor more than every 30 minutes
        return
    repetition = Repetition(in_a_row + 1, sum(2 if row.has_waittimes else 1 for row in grouping.rows), difference)
    # repetition.min_height = sum(2 if row.has_waittimes else 1 for row in grouping.rows if not row.is_minor())
    grouping.rows[0].times[i - in_a_row - 2] = repetition
    for j in range(i - in_a_row - 1, i - 1):
        grouping.rows[0].times[j] = None
    for j in range(i - in_a_row - 2, i - 1):
        for row in grouping.rows[1:]:
            row.times[j] = None


class Grouping:
    def __init__(self, inbound=False):
        self.heads = []
        self.rows = []
        self.trips = []
        self.inbound = inbound
        self.column_feet = {}

    def __str__(self):
        if self.inbound:
            return 'Inbound'
        return 'Outbound'

    def has_minor_stops(self):
        for row in self.rows:
            if row.timing_status == 'OTH':
                return True

    def get_order(self):
        if self.trips:
            return self.trips[0].start

    def handle_trip(self, trip):
        rows = self.rows
        if rows:
            x = len(rows[0].times)
        else:
            x = 0
        previous_list = [row.stop.atco_code for row in rows]
        current_list = [stoptime.stop_code for stoptime in trip.stoptime_set.all()]
        diff = differ.compare(previous_list, current_list)

        y = 0  # how many rows along we are

        for stoptime in trip.stoptime_set.all():
            if y < len(rows):
                existing_row = rows[y]
            else:
                existing_row = None

            instruction = next(diff)

            while instruction[0] in '-?':
                if instruction[0] == '-':
                    y += 1
                    if y < len(rows):
                        existing_row = rows[y]
                    else:
                        existing_row = None
                instruction = next(diff)

            assert instruction[2:] == stoptime.stop_code

            if instruction[0] == '+':
                row = Row(Stop(stoptime.stop_code), [''] * x)
                row.timing_status = stoptime.timing_status
                if not existing_row:
                    rows.append(row)
                else:
                    rows = self.rows = rows[:y] + [row] + rows[y:]
                existing_row = row
            else:
                row = existing_row
                assert instruction[2:] == existing_row.stop.atco_code

            cell = Cell(stoptime, stoptime.arrival, stoptime.departure)
            row.times.append(cell)

            y += 1

        cell.last = True

        if x:
            for row in rows:
                if len(row.times) == x:
                    row.times.append('')

    def do_heads_and_feet(self):
        previous_trip = None
        previous_notes = None
        previous_note_ids = None
        in_a_row = 0
        prev_difference = None

        for i, trip in enumerate(self.trips):
            difference = None
            notes = trip.notes.all()
            note_ids = {note.id for note in notes}
            for note in notes:
                if note.id in self.column_feet:
                    if note in previous_notes:
                        self.column_feet[note.id][-1].span += 1
                    else:
                        self.column_feet[note.id].append(ColumnFoot(note))
                elif i:
                    self.column_feet[note.id] = [ColumnFoot(None, i), ColumnFoot(note)]
                else:
                    self.column_feet[note.id] = [ColumnFoot(note)]
            for key in self.column_feet:
                if not any(key == note.id for note in notes):
                    if not self.column_feet[key][-1].notes:
                        # expand existing empty cell
                        self.column_feet[key][-1].span += 1
                    else:
                        # new empty cell
                        self.column_feet[key].append(ColumnFoot(None, 1))

            if previous_trip:
                if previous_trip.route_id != trip.route_id:
                    if self.heads:
                        self.heads.append(ColumnHead(previous_trip.route, i - sum(head.span for head in self.heads)))
                    else:
                        self.heads.append(ColumnHead(previous_trip.route, i))

                if previous_note_ids != note_ids:
                    if in_a_row > 1:
                        abbreviate(self, i, in_a_row - 1, prev_difference)
                    in_a_row = 0
                elif trip.journey_pattern and previous_trip.journey_pattern == trip.journey_pattern:
                    difference = trip.start - previous_trip.start
                    if difference == prev_difference:
                        in_a_row += 1
                    else:
                        if in_a_row > 1:
                            abbreviate(self, i, in_a_row - 1, prev_difference)
                        in_a_row = 0
                else:
                    if in_a_row > 1:
                        abbreviate(self, i, in_a_row - 1, prev_difference)
                    in_a_row = 0

            prev_difference = difference
            previous_trip = trip
            previous_notes = notes
            previous_note_ids = note_ids

        if self.heads:  # or (previous_trip and previous_trip.route_id != self.parent.route_id):
            self.heads.append(ColumnHead(previous_trip.route.service,
                                         len(self.trips) - sum(head.span for head in self.heads)))

        if in_a_row > 1:
            abbreviate(self, len(self.trips), in_a_row - 1, prev_difference)

        for row in self.rows:
            # remove 'None' cells created during the abbreviation process
            # (actual empty cells will contain an empty string '')
            row.times = [time for time in row.times if time is not None]


class ColumnHead:
    def __init__(self, service, span):
        self.service = service
        self.span = span


class ColumnFoot:
    def __init__(self, note, span=1):
        self.notes = note and note.text
        self.span = span


class Row:
    def __init__(self, stop, times=[]):
        self.stop = stop
        self.times = times


class Stop:
    def __init__(self, atco_code):
        self.atco_code = atco_code

    def __str__(self):
        return self.atco_code


def format_timedelta(timedelta):
    timedelta = str(timedelta)[:-3]
    timedelta = timedelta.replace('1 day, ', '', 1)
    if len(timedelta) == 4:
        return '0' + timedelta
    return timedelta


class Cell:
    last = False

    def __init__(self, stoptime, arrival, departure):
        self.stoptime = stoptime
        self.arrival = arrival
        self.departure = departure
        self.wait_time = arrival and departure and arrival != departure

    def __repr__(self):
        return format_timedelta(self.arrival)

    def departure_time(self):
        return format_timedelta(self.departure)
