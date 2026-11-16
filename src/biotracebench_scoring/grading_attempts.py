"""Bounded replacement of transport-interrupted grading requests on explicit resume."""
from decimal import Decimal
from pathlib import Path
from dataclasses import dataclass

from model_conversation.archive import digest, event, read, write
from model_api import dispatch
from .grading_archives import assess, assessment_path


@dataclass(frozen=True)
class AttemptFailureContext:
    attempt: Path
    response: object = None
    dispatch_state: str | None = None


def retry_limit(budget):
    value = budget.get('max_network_retries_per_output', 0)
    if type(value) is not int or value < 0:
        raise ValueError('max_network_retries_per_output must be a nonnegative integer')
    return value


class GradingAttempts:
    def __init__(self, out, transport, costs, cap, single, total, reserve, control, retries):
        self.out, self.transport, self.costs = Path(out), transport, costs
        self.cap, self.single, self.total = cap, single, total
        self.reserve, self.control, self.retries = reserve, control, retries
        self.failure = None
        self.prepare_send = getattr(transport, 'prepare_send', None)
        self.check_send = getattr(transport, 'check_send', None)

    def failed(self, error, folder, state=None):
        """Keep attempt context without modifying exceptions owned by the SDK."""
        self.failure = AttemptFailureContext(folder, getattr(error, 'response', None),
            state if state is not None else getattr(error, 'dispatch_state', None))
        return self.failure

    def key(self, folder):
        return str(folder.relative_to(self.out))

    def folders(self):
        root = self.out/'attempts'
        return sorted([*root.glob('*/reservation.json'),
                       *root.glob('*/network-retries/*/reservation.json')])

    def count(self):
        return sum(dispatch.state(p.parent)!='not_sent' for p in self.folders())

    def not_sent(self):
        return [{'attempt':self.key(p.parent), 'consumption':'not_sent',
                 'exact_cny':'0', 'upper_cny':'0', 'generated_requests':0}
                for p in self.folders() if dispatch.state(p.parent)=='not_sent']

    def unknown(self):
        known = {c.get('attempt', 'attempts/'+c['output']) for c in self.costs}
        rows = []
        for reservation in self.folders():
            folder = reservation.parent
            interrupted = folder/'network-interruption.json'
            check = assessment_path(self.out, self.key(folder))
            conflict = check.exists() and read(check)['status']=='conflict'
            state = dispatch.state(folder)
            if self.key(folder) in known or state=='not_sent' and not conflict:
                continue
            saved = read(reservation)
            if interrupted.exists() and read(interrupted).get('reservation_identity') != digest(saved):
                raise ValueError('Network interruption/reservation identity changed')
            rows.append({'attempt':self.key(folder), 'consumption':'unknown',
                'reason':('archive_conflict' if conflict else 'transport_interrupted' if interrupted.exists()
                          else 'legacy_submission_unknown' if state=='legacy_unknown'
                          else 'dispatch_started_without_accounted_usage'),
                'reserve_upper_cny':saved['reserve_upper_cny'],
                'exact_cny':None, 'billed_actual':None})
        return rows

    def unknown_upper(self):
        return sum((Decimal(r['reserve_upper_cny']) for r in self.unknown()), Decimal(0))

    def save_state(self):
        unknown = self.unknown()
        known = sum((Decimal(c['upper_cny']) for c in self.costs), Decimal(0))
        held = sum((Decimal(r['reserve_upper_cny']) for r in unknown), Decimal(0))
        write(self.out/'network-recovery.json', {
            'protocol':'biotracebench-grading-network-recovery-1',
            'max_network_retries_per_output':self.retries,
            'trigger':'explicit_grade_run_resume', 'automatic_in_call_retry':False,
            'server_result_lookup':'not_supported_by_current_chat_backend',
            'reserved_requests':self.count(), 'unknown_requests':unknown,
            'local_reservations':len(self.folders()), 'not_sent_requests':self.not_sent(),
            'known_usage_upper_cny':str(known), 'unknown_reserved_upper_cny':str(held),
            'budget_committed_upper_cny':str(known+held),
            'exact_cny':None, 'billed_actual':None})

    def _reservation(self, packet, index):
        value = {'packet_identity':digest(packet),'reserve_upper_cny':str(self.reserve),
                 'output_control':self.control}
        if index:
            value.update(network_retry=index, replaces='attempts/'+packet['id'])
        return value

    def _select(self, base, packet, index):
        target = {'packet_identity':digest(packet), 'attempt_index':index}
        path = base/'selected-attempt.json'
        if path.exists() and read(path) != target:
            raise ValueError('Selected grading attempt changed')
        write(path, target)

    def _recover(self, base, packet, folder, index):
        if read(folder/'reservation.json') != self._reservation(packet, index):
            raise ValueError('Grading reservation changed')
        try:
            assess(self.out, self.transport, packet, folder)
            response = self.transport.recover(packet['request'], folder)
        except Exception as error:
            context = self.failed(error, folder)
            if context.response is not None:
                self._select(base, packet, index)
            raise
        if response is not None:
            self._select(base, packet, index)
            event(self.out, 'response_recovered', output=packet['id'], attempt=self.key(folder))
        return response

    def obtain(self, packet, *, offline):
        self.failure = None
        base = self.out/'attempts'/packet['id']
        paths = [base]
        retries = sorted((base/'network-retries').iterdir()) if (base/'network-retries').exists() else []
        for index, folder in enumerate(retries, 1):
            if not folder.is_dir() or folder.name != f'{index:04d}':
                raise ValueError('Network retry directories changed')
            paths.append(folder)
        selected = base/'selected-attempt.json'
        if selected.exists():
            stamp = read(selected)
            index = stamp.get('attempt_index')
            if (stamp.get('packet_identity') != digest(packet) or type(index) is not int
                    or not 0 <= index < len(paths)):
                raise ValueError('Selected grading attempt identity changed')
            response = self._recover(base, packet, paths[index], index)
            if response is None:
                raise RuntimeError('Selected archived response is incomplete; no network retry')
            return paths[index], response
        for index, folder in enumerate(paths):
            marker = folder/'reservation.json'
            if not marker.exists():
                if index or folder.exists():
                    if (self.prepare_send is None
                            or dispatch.state(folder)!='not_sent' or index!=len(paths)-1):
                        raise RuntimeError('Unreserved attempt directory requires review; no resend')
                break
            response = self._recover(base, packet, folder, index)
            if response is not None:
                return folder, response
            if dispatch.state(folder)=='not_sent':
                if self.prepare_send is None or index!=len(paths)-1:
                    raise RuntimeError('Unsent attempt cannot be continued by this backend/layout')
                break
            interrupted = folder/'network-interruption.json'
            if not interrupted.exists():
                raise RuntimeError('Reserved request has no complete response; execution/cost unknown; no resend')
            if read(interrupted).get('reservation_identity') != digest(read(marker)):
                raise ValueError('Network interruption/reservation identity changed')
        else:
            if offline:
                raise RuntimeError('Reserved request has no complete response; execution/cost unknown; offline recovery cannot resend')
            if len(paths)-1 >= self.retries:
                raise RuntimeError('Network retry limit reached; execution/cost unknown; no resend')
            index = len(paths)
            folder = base/'network-retries'/f'{index:04d}'
        if offline:
            raise RuntimeError('Offline recovery cannot submit unexecuted grading requests')
        try:
            if self.check_send:
                self.check_send(packet['request'])
        except Exception as error:
            self.failed(error, folder, 'not_sent')
            event(self.out,'request_not_sent',output=packet['id'],reason=str(error),
                  generated_requests=0,exact_cny='0',automatic_retry=False)
            self.save_state()
            raise
        known = sum((Decimal(c['upper_cny']) for c in self.costs), Decimal(0))
        if (self.count() >= self.cap or self.reserve > self.single
                or known+self.unknown_upper()+self.reserve > self.total):
            raise RuntimeError('Request/count/total budget reached before submission; unknown requests retain their reservations')
        reservation = self._reservation(packet, index)
        try:
            if self.prepare_send:self.prepare_send(packet['request'],folder)
            else:folder.mkdir(parents=True,exist_ok=True)
        except Exception as error:
            state=getattr(error,'dispatch_state',None)
            if state is None:
                state='not_sent' if dispatch.state(folder)=='not_sent' else 'unknown'
            context=self.failed(error,folder,state)
            event(self.out,'send_preparation_failed',output=packet['id'],attempt=self.key(folder),
                  dispatch_state=context.dispatch_state,reason=str(error),automatic_retry=False)
            self.save_state()
            raise
        marker=folder/'reservation.json'
        if marker.exists():
            if read(marker)!=reservation:raise ValueError('Grading reservation changed')
        else:write(marker,reservation)
        event(self.out, 'request_reserved', output=packet['id'], attempt=self.key(folder),
              network_retry=index, reserve_upper_cny=str(self.reserve), output_control=self.control)
        try:
            response = self.transport.invoke(packet['request'], folder)
            assess(self.out, self.transport, packet, folder)
        except Exception as error:
            response = self.failed(error, folder).response
            try:
                assess(self.out, self.transport, packet, folder)
            except Exception as archive_error:
                self.failed(archive_error, folder)
                raise archive_error from None
            if response is not None:
                self._select(base, packet, index)
            elif dispatch.state(folder)=='not_sent':
                self.failed(error, folder, 'not_sent')
                event(self.out,'request_not_sent',output=packet['id'],attempt=self.key(folder),
                      reason=str(error),generated_requests=0,exact_cny='0',automatic_retry=False)
                self.save_state()
            elif getattr(error, 'category', None) == 'transport_interrupted':
                write(folder/'network-interruption.json', {
                    'reservation_identity':digest(reservation), 'consumption':'unknown',
                    'reason':'Transport interrupted before a complete response was archived'})
                self.save_state()
                event(self.out, 'network_interrupted', output=packet['id'], attempt=self.key(folder),
                      consumption='unknown', reserve_upper_cny=str(self.reserve),
                      automatic_in_call_retry=False)
            else:
                self.save_state()
            raise
        self._select(base, packet, index)
        return folder, response
