import EventList from '../components/events/EventList'
import t from '../utils/translations'

export default function EventsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">{t.events.title}</h1>
      <EventList />
    </div>
  )
}
