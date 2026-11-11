import { useCallback, useEffect, useMemo, useState } from 'react';
import { isAxiosError } from 'axios';
import { buildScheduleRequest, schedulingAPI, schedulingService } from '../services/schedulingApi';
import { requestErrorMessage } from '../services/requestError';
import {
  ScheduleFormValues,
  ScheduledExperiment,
  NotificationContact,
  NotificationContactPayload,
  NotificationSettings,
  NotificationSettingsUpdatePayload,
} from '../types/scheduling';

const sortContacts = (list: NotificationContact[]) =>
  [...list].sort((a, b) => a.is_active !== b.is_active ? (a.is_active ? -1 : 1) : a.display_name.localeCompare(b.display_name));

/**
 * Owns the schedule lists, the selection and the notification contacts and settings.
 * Robot and queue status belong to the frame (useRobotStatusContext); panels that only read for
 * themselves (delivery log, method library, recovery actions) call their routes directly.
 */
const useScheduling = () => {
  const [schedules, setSchedules] = useState<ScheduledExperiment[]>([]);
  const [archivedSchedules, setArchivedSchedules] = useState<ScheduledExperiment[]>([]);
  // One selection serves Schedules, Archived, History and the delete dialog; it is dropped
  // when neither list holds it after a reload.
  const [selectedScheduleId, setSelectedScheduleId] = useState<string | null>(null);
  const selectedSchedule = useMemo(() => [...schedules, ...archivedSchedules]
    .find(schedule => schedule.schedule_id === selectedScheduleId) ?? null, [schedules, archivedSchedules, selectedScheduleId]);
  const [loading, setLoading] = useState(false);
  const [archivedLoading, setArchivedLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [archivedError, setArchivedError] = useState<string | null>(null);
  const [contacts, setContacts] = useState<NotificationContact[]>([]);
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings | null>(null);
  const [notificationSettingsLoading, setNotificationSettingsLoading] = useState(false);

  /** `focus` selects that schedule (null clears the selection); undefined keeps it. */
  const loadSchedules = useCallback(async (focus?: string | null): Promise<void> => {
    setLoading(true);
    setError(null);
    const result = await schedulingService.getAllSchedules(false, false);
    if (result.error) setError(result.error);
    else {
      setSchedules(result.schedules);
      if (focus !== undefined) setSelectedScheduleId(focus);
    }
    setLoading(false);
  }, []);

  const loadArchivedSchedules = useCallback(async (): Promise<void> => {
    setArchivedLoading(true);
    setArchivedError(null);
    const result = await schedulingService.getArchivedSchedules();
    if (result.error) setArchivedError(result.error);
    else setArchivedSchedules(result.schedules);
    setArchivedLoading(false);
  }, []);

  /** Throws the server's message, so the form keeps its draft and shows why. */
  const createSchedule = useCallback(async (values: ScheduleFormValues): Promise<void> => {
    const result = await schedulingService.createSchedule(values);
    if (result.error) throw new Error(result.error);
    await loadSchedules(result.scheduleId);
  }, [loadSchedules]);

  /** `version` is the updated_at the form opened; a 409 is rethrown as is for the form to explain. */
  const updateSchedule = useCallback(async (scheduleId: string, values: ScheduleFormValues, version: string): Promise<void> => {
    try {
      const { data } = await schedulingAPI.updateSchedule(scheduleId, { ...buildScheduleRequest(values), expected_updated_at: version });
      if (!data.success) throw new Error(data.message || 'Failed to update schedule');
    } catch (err) {
      if (!isAxiosError(err)) throw err;
      if (err.response?.status === 409) {
        await loadSchedules(scheduleId);
        throw err;
      }
      throw new Error(requestErrorMessage(err, 'Failed to update schedule'));
    }
    await loadSchedules(scheduleId);
  }, [loadSchedules]);

  const deleteSchedule = useCallback(async (schedule: ScheduledExperiment): Promise<void> => {
    setDeleting(true);
    const result = await schedulingService.deleteSchedule(schedule.schedule_id, schedule.updated_at || undefined);
    // Reload either way: a refused delete may mean the schedule changed or went.
    await loadSchedules(result.error ? undefined : null);
    await loadArchivedSchedules();
    if (result.error) setError(result.error);
    setDeleting(false);
  }, [loadArchivedSchedules, loadSchedules]);

  const archiveSchedule = useCallback(async (schedule: ScheduledExperiment, archived: boolean): Promise<void> => {
    setError(null);
    const result = await schedulingService.archiveSchedule(schedule.schedule_id, archived, schedule.updated_at || undefined);
    if (result.error) {
      setError(result.error);
      return;
    }
    await loadSchedules(archived ? null : schedule.schedule_id);
    await loadArchivedSchedules();
  }, [loadArchivedSchedules, loadSchedules]);

  const loadContacts = useCallback(async (includeInactive = true): Promise<{ contacts?: NotificationContact[]; error?: string }> => {
    const result = await schedulingService.getNotificationContacts(includeInactive);
    if (result.error) {
      setError(result.error);
      return { error: result.error };
    }
    setContacts(sortContacts(result.contacts));
    return { contacts: result.contacts };
  }, []);

  const loadNotificationSettings = useCallback(async (): Promise<{ settings?: NotificationSettings | null; error?: string }> => {
    setNotificationSettingsLoading(true);
    const result = await schedulingService.getNotificationSettings();
    setNotificationSettingsLoading(false);
    if (result.error) {
      setError(result.error);
      return { error: result.error };
    }
    setNotificationSettings(result.settings ?? null);
    return { settings: result.settings ?? null };
  }, []);

  const updateNotificationSettings = useCallback(async (payload: NotificationSettingsUpdatePayload): Promise<{ settings?: NotificationSettings; error?: string }> => {
    setNotificationSettingsLoading(true);
    const result = await schedulingService.updateNotificationSettings(payload);
    setNotificationSettingsLoading(false);
    if (result.error) {
      setError(result.error);
      return { error: result.error };
    }
    if (result.settings) setNotificationSettings(result.settings);
    return { settings: result.settings };
  }, []);

  const sendNotificationTestEmail = useCallback((recipient: string) => schedulingService.sendNotificationTestEmail(recipient), []);

  const createContact = useCallback(async (payload: NotificationContactPayload): Promise<{ contact?: NotificationContact; error?: string }> => {
    const result = await schedulingService.createNotificationContact(payload);
    if (!result.contact) {
      setError(result.error!);
      return { error: result.error };
    }
    setContacts(prev => sortContacts([...prev, result.contact!]));
    return { contact: result.contact };
  }, []);

  const updateContact = useCallback(async (contactId: string, payload: NotificationContactPayload): Promise<{ contact?: NotificationContact; error?: string }> => {
    const result = await schedulingService.updateNotificationContact(contactId, payload);
    if (!result.contact) {
      setError(result.error!);
      return { error: result.error };
    }
    setContacts(prev => sortContacts(prev.map(contact => (contact.contact_id === contactId ? result.contact! : contact))));
    return { contact: result.contact };
  }, []);

  const deleteContact = useCallback(async (contactId: string): Promise<{ success: boolean; error?: string }> => {
    const result = await schedulingService.deleteNotificationContact(contactId);
    if (!result.success) {
      setError(result.error!);
      return result;
    }
    setContacts(prev => prev.filter(contact => contact.contact_id !== contactId));
    return { success: true };
  }, []);

  const selectSchedule = useCallback((schedule: ScheduledExperiment | null) => {
    setSelectedScheduleId(schedule?.schedule_id ?? null);
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    setArchivedError(null);
  }, []);

  useEffect(() => {
    void loadSchedules();
    void loadArchivedSchedules();
    void loadContacts(false);
  }, [loadSchedules, loadArchivedSchedules, loadContacts]);

  const actions = useMemo(() => ({
    loadSchedules,
    loadArchivedSchedules,
    createSchedule,
    updateSchedule,
    deleteSchedule,
    archiveSchedule,
    loadContacts,
    createContact,
    updateContact,
    deleteContact,
    loadNotificationSettings,
    updateNotificationSettings,
    sendNotificationTestEmail,
    selectSchedule,
    clearError,
  }), [loadSchedules, loadArchivedSchedules, createSchedule, updateSchedule, deleteSchedule, archiveSchedule, loadContacts,
    createContact, updateContact, deleteContact, loadNotificationSettings, updateNotificationSettings, sendNotificationTestEmail,
    selectSchedule, clearError]);

  return {
    state: {
      schedules,
      archivedSchedules,
      selectedSchedule,
      loading,
      archivedLoading,
      deleting,
      error,
      archivedError,
      contacts,
      notificationSettings,
      notificationSettingsLoading,
    },
    actions,
  };
};

export { useScheduling };
export default useScheduling;
