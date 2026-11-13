import 'package:flutter/material.dart';
import 'package:airway/core/theme/airway_colors.dart';
import 'package:airway/features/location/data/location_api.dart';

class SupportScreen extends StatefulWidget {
  const SupportScreen({super.key});
  @override
  State<SupportScreen> createState() => _SupportScreenState();
}
class _SupportScreenState extends State<SupportScreen> {
  List<Map<String,dynamic>> _tickets=[];
  bool _loading=true;
  String? _error;
  @override
  void initState(){super.initState();_load();}
  Future<void> _load() async {
    setState(()=>_loading=true); 
    try { final raw=await LocationApi.request('/api/v1/support/tickets/');
      final list=raw is Map ? raw['results'] : raw;
      if(mounted)setState(()=>_tickets=(list as List? ?? []).whereType<Map>().map((e)=>Map<String,dynamic>.from(e)).toList());
    } catch(_){if(mounted)setState(()=>_error='Could not load support requests. Please try again.');}
    finally{if(mounted)setState(()=>_loading=false);}
  }
  Future<void> _newTicket() async {
    final subject=TextEditingController(), message=TextEditingController();
    String category='other';
    final result=await showDialog<bool>(context:context,builder:(ctx)=>StatefulBuilder(builder:(ctx,setDialog)=>AlertDialog(
      title:const Text('Contact AIRway Support'),
      content:SizedBox(width:420,child:SingleChildScrollView(child:Column(mainAxisSize:MainAxisSize.min,children:[
        DropdownButtonFormField<String>(value:category,decoration:const InputDecoration(labelText:'Issue category'),items:const [
          DropdownMenuItem(value:'payment',child:Text('Payment and refund')),
          DropdownMenuItem(value:'booking',child:Text('Booking problem')),
          DropdownMenuItem(value:'service',child:Text('Service quality')),
          DropdownMenuItem(value:'account',child:Text('Account and profile')),
          DropdownMenuItem(value:'safety',child:Text('Safety concern')),
          DropdownMenuItem(value:'worker',child:Text('Worker or customer issue')),
          DropdownMenuItem(value:'other',child:Text('Other')),
        ],onChanged:(v)=>setDialog(()=>category=v??'other')),
        TextField(controller:subject,decoration:const InputDecoration(labelText:'Subject'),maxLength:160),
        TextField(controller:message,decoration:const InputDecoration(labelText:'Describe your issue'),minLines:3,maxLines:6,maxLength:5000),
      ]))),
      actions:[TextButton(onPressed:()=>Navigator.pop(ctx,false),child:const Text('Cancel')),FilledButton(onPressed:()=>Navigator.pop(ctx,true),child:const Text('Send request'))],
    )));
    if(result!=true)return;
    if(subject.text.trim().length<4||message.text.trim().length<5){if(mounted)ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Please enter a subject and a detailed message.')));return;}
    try{
      await LocationApi.request('/api/v1/support/tickets/',method:'POST',data:{'category':category,'subject':subject.text.trim(),'message':message.text.trim()});
      if(mounted)ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content:Text('Your message has reached AIRway Support.')));
      await _load();
    }catch(e){if(mounted)ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('Could not send request: $e')));}
  }
  Future<void> _open(Map<String,dynamic> ticket) async {
    final id=ticket['id']; if(id==null)return;
    final reply=TextEditingController();
    await showModalBottomSheet<void>(context:context,isScrollControlled:true,builder:(ctx)=>StatefulBuilder(builder:(ctx,setSheet)=>Padding(
      padding:EdgeInsets.fromLTRB(18,18,18,MediaQuery.of(ctx).viewInsets.bottom+18),
      child:SafeArea(child:Column(mainAxisSize:MainAxisSize.min,crossAxisAlignment:CrossAxisAlignment.start,children:[
        Text(ticket['ticket_number']?.toString()??'Support request',style:Theme.of(ctx).textTheme.titleLarge),
        Text(ticket['status_display']?.toString()??ticket['status']?.toString()??'',style:const TextStyle(color:AirwayColors.primary)),
        const SizedBox(height:12),
        Flexible(child:FutureBuilder<dynamic>(future:LocationApi.request('/api/v1/support/tickets/$id/'),builder:(ctx,snap){
          if(!snap.hasData)return const Center(child:CircularProgressIndicator());
          final data=Map<String,dynamic>.from(snap.data as Map); final rows=(data['messages'] as List? ?? []);
          return ListView(shrinkWrap:true,children:rows.whereType<Map>().map((m)=>Card(child:ListTile(title:Text(m['sender_name']?.toString()??'AIRway'),subtitle:Text(m['message']?.toString()??'')))).toList());
        })),
        TextField(controller:reply,minLines:2,maxLines:4,decoration:const InputDecoration(hintText:'Write a reply...')),
        Align(alignment:Alignment.centerRight,child:FilledButton(onPressed:()async{
          final text=reply.text.trim();if(text.length<5)return;
          try{await LocationApi.request('/api/v1/support/tickets/$id/',method:'POST',data:{'message':text});if(ctx.mounted)Navigator.pop(ctx);await _load();}
          catch(e){if(ctx.mounted)ScaffoldMessenger.of(context).showSnackBar(SnackBar(content:Text('Reply failed: $e')));}
        },child:const Text('Send reply'))),
      ])),
    )));
  }
  @override
  Widget build(BuildContext context)=>Scaffold(
    appBar:AppBar(title:const Text('AIRway Help & Support'),actions:[IconButton(onPressed:_load,icon:const Icon(Icons.refresh))]),
    floatingActionButton:FloatingActionButton.extended(onPressed:_newTicket,icon:const Icon(Icons.support_agent),label:const Text('New request')),
    body:_loading?const Center(child:CircularProgressIndicator()):_error!=null?Center(child:Column(mainAxisSize:MainAxisSize.min,children:[Text(_error!),FilledButton(onPressed:_load,child:const Text('Retry'))])):_tickets.isEmpty?const Center(child:Text('No support requests yet. Tap New request if you need help.')):RefreshIndicator(onRefresh:_load,child:ListView.builder(padding:const EdgeInsets.all(16),itemCount:_tickets.length,itemBuilder:(ctx,i){final t=_tickets[i];return Card(child:ListTile(leading:const Icon(Icons.support_agent,color:AirwayColors.primary),title:Text(t['subject']?.toString()??'Support request'),subtitle:Text('${t['ticket_number']??''} • ${t['status_display']??t['status']??''}'),trailing:const Icon(Icons.chevron_right),onTap:()=>_open(t)));})),
  );
}
